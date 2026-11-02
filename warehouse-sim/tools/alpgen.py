"""Tiny writer for AnyLogic 8.9 .alp files (XML), built from the structures used by the
AnyLogic 8.9 example models. Only what the assembly-line models need is implemented.

Every piece of Java that goes into the model is also registered in a "shadow" Java source
(see Shadow) that is compiled against the real AnyLogic engine jars, so type errors are
caught before the model is opened in AnyLogic.
"""
from __future__ import annotations
import itertools
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

PML = "com.anylogic.libraries.processmodeling"

# Block definitions (generic parameters, parameters, kinds, Java types, callback arguments) are read from
# the Process Modeling Library itself (library.xml in ProcessModelingLibrary.jar), see extract_pml_spec.py.
import json as _json, pathlib as _pathlib, re as _re
SPEC = _json.loads((_pathlib.Path(__file__).parent / "pml_spec.json").read_text())
GENERIC_ID = {c: [g[0] for g in v["generics"]] for c, v in SPEC.items()}
GENERIC_NAMES = {c: [g[1] for g in v["generics"]] for c, v in SPEC.items()}
PARAMS = {c: [p["name"] for p in v["params"]] for c, v in SPEC.items()}
_PSPEC = {c: {p["name"]: p for p in v["params"]} for c, v in SPEC.items()}
_QUALIFY = {"AnimationStaticLocationProvider": "com.anylogic.engine.markup.AnimationStaticLocationProvider"}


def code_sig(cls, pname, types):
    """(kind, return type, [(type, name)]) of a code field, with the block's generics substituted."""
    p = _PSPEC[cls][pname]
    sub = dict(zip(GENERIC_NAMES[cls], types))

    def t(x):
        x = _QUALIFY.get(x, x)
        return _re.sub(r"\b(T\d?|TContainer)\b", lambda m: sub.get(m.group(1), "Agent"), x)

    rtype = "double" if (p["type"] == "" and p["unit"] != "NONE") else t(p["type"])
    kind = "action" if p["kind"] == "ACTION" else "value"
    args = [(t(a[1]), a[0]) for a in p["args"]] if p["kind"] != "STATIC" else []
    return kind, rtype, args


def cd(s):
    """CDATA wrapper (splits a literal ']]>' if ever present)."""
    return "<![CDATA[" + str(s).replace("]]>", "]]]]><![CDATA[>") + "]]>"


def color(argb):
    """'#RRGGBB' or int -> signed 32-bit ARGB int as AnyLogic stores it."""
    if isinstance(argb, str):
        v = int(argb.lstrip("#"), 16) | 0xFF000000
    else:
        v = argb
    return v - (1 << 32) if v >= (1 << 31) else v


class Ids:
    def __init__(self, start=1762300000000):
        self.c = itertools.count(start)

    def __call__(self):
        return next(self.c)


# ----------------------------------------------------------------------------- shadow java
# The import block AnyLogic 8.9 puts at the top of every generated agent class
GENERATED_IMPORTS = """import java.io.Serializable;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Calendar;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.Currency;
import java.util.Date;
import java.util.Enumeration;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Hashtable;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;
import java.util.Locale;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Random;
import java.util.Set;
import java.util.SortedMap;
import java.util.SortedSet;
import java.util.Stack;
import java.util.Timer;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.Vector;
import java.awt.Color;
import java.awt.Font;
import com.anylogic.engine.connectivity.ResultSet;
import com.anylogic.engine.connectivity.Statement;
import com.anylogic.engine.elements.*;
import com.anylogic.engine.markup.Network;
import com.anylogic.engine.Position;
import com.anylogic.engine.markup.PedFlowStatistics;
import com.anylogic.engine.markup.DensityMap;
import static java.lang.Math.*;
import static com.anylogic.engine.UtilitiesArray.*;
import static com.anylogic.engine.UtilitiesCollection.*;
import static com.anylogic.engine.presentation.UtilitiesColor.*;
import static com.anylogic.engine.HyperArray.*;
import com.anylogic.engine.*;
import com.anylogic.engine.analysis.*;
import com.anylogic.engine.connectivity.*;
import com.anylogic.engine.database.*;
import com.anylogic.engine.gis.*;
import com.anylogic.engine.markup.*;
import com.anylogic.engine.routing.*;
import com.anylogic.engine.presentation.*;
import com.anylogic.engine.gui.*;
import com.anylogic.libraries.processmodeling.*;
"""

class Shadow:
    """Collects all Java snippets per agent class and emits a compilable 'shadow' source."""

    def __init__(self, package):
        self.package = package
        self.classes = {}  # name -> dict(fields=[], methods=[], extra=[])
        self.n = itertools.count(1)

    def cls(self, name):
        return self.classes.setdefault(name, dict(fields=[], methods=[], extra=[], imports=[]))

    def field(self, cls, decl):
        self.cls(cls)["fields"].append(decl)

    def method(self, cls, src):
        self.cls(cls)["methods"].append(src)

    def snippet(self, cls, kind, rtype, locals_, code, where):
        args = ", ".join(f"{t} {n}" for t, n in locals_)
        i = next(self.n)
        if kind == "value":
            body = f"return {code};" if rtype != "void" else f"{code};"
        else:
            body = code
        self.method(cls, f"  // {where}\n  {rtype} _snippet{i}({args}) {{\n{body}\n  }}")

    def source(self, cls):
        c = self.classes[cls]
        imports = "\n".join(c["imports"])
        return (f"package {self.package};\n" + GENERATED_IMPORTS + f"{imports}\n"
                f"@SuppressWarnings(\"all\")\npublic class {cls} extends Agent {{\n"
                + "\n".join("  " + f for f in c["fields"]) + "\n"
                + "\n".join(c["methods"]) + "\n"
                + "\n".join(c["extra"]) + "\n}\n")


# ----------------------------------------------------------------------------- elements
@dataclass
class Block:
    name: str
    cls: str
    x: float
    y: float
    types: tuple            # agent type(s) for the generic parameter(s)
    params: dict            # name -> xml <Value ...> string


class AgentClass:
    def __init__(self, model, name, entity=True):
        self.model, self.name = model, name
        self.id = model.ids()
        self.generic_id = model.ids()
        self.level_id = model.ids()
        self.scale_id = model.ids()
        self.links_id = model.ids()
        self.variables, self.functions, self.blocks, self.connectors = [], [], [], []
        self.shapes, self.markup_level, self.network_paths = [], [], []
        self.startup, self.destroy, self.additional, self.imports = "", "", "", ""
        self.entity = entity
        self.shadow = model.shadow
        model.shadow.cls(name)

    # -- variables / parameters / functions
    def plain_var(self, name, jtype, init=None, x=0, y=0, public=True):
        v = (f'<Variable Class="PlainVariable">\n<Id>{self.model.ids()}</Id>\n<Name>{cd(name)}</Name>\n'
             f'<X>{x}</X><Y>{y}</Y>\n<Label><X>10</X><Y>0</Y></Label>\n<PublicFlag>false</PublicFlag>\n'
             f'<PresentationFlag>true</PresentationFlag>\n<ShowLabel>true</ShowLabel>\n'
             f'<Properties SaveInSnapshot="true" Constant="false" AccessType="public" StaticVariable="false">\n'
             f'<Type>{cd(jtype)}</Type>\n')
        if init is not None:
            v += f'<InitialValue Class="CodeValue">\n<Code>{cd(init)}</Code>\n</InitialValue>\n'
        v += '</Properties>\n</Variable>'
        self.variables.append(v)
        self.shadow.field(self.name, f"public {jtype} {name}" + (f" = {init};" if init is not None else ";"))

    def parameter(self, name, jtype, default, x=0, y=0):
        pid = self.model.ids()
        v = (f'<Variable Class="Parameter">\n<Id>{pid}</Id>\n<Name>{cd(name)}</Name>\n'
             f'<X>{x}</X><Y>{y}</Y>\n<Label><X>10</X><Y>0</Y></Label>\n<PublicFlag>false</PublicFlag>\n'
             f'<PresentationFlag>true</PresentationFlag>\n<ShowLabel>true</ShowLabel>\n'
             f'<Properties SaveInSnapshot="true" ModificatorType="STATIC">\n<Type>{cd(jtype)}</Type>\n'
             f'<UnitType>{cd("NONE")}</UnitType>\n<SdArray>false</SdArray>\n'
             f'<DefaultValue Class="CodeValue">\n<Code>{cd(default)}</Code>\n</DefaultValue>\n'
             f'<ParameterEditor>\n<Id>{self.model.ids()}</Id>\n<EditorContolType>TEXT_BOX</EditorContolType>\n'
             f'<MinSliderValue>{cd("0")}</MinSliderValue>\n<MaxSliderValue>{cd("100")}</MaxSliderValue>\n'
             f'<DelimeterType>NO_DELIMETER</DelimeterType>\n</ParameterEditor>\n</Properties>\n</Variable>')
        self.variables.append(v)
        self.shadow.field(self.name, f"public {jtype} {name} = {default};")
        return pid

    def function(self, name, ret, args, body, x=0, y=0, doc=""):
        """ret=None -> void. args: list of (type, name)."""
        a = "".join(f'<Parameter>\n<Name>{cd(n)}</Name>\n<Type>{cd(t)}</Type>\n</Parameter>\n' for t, n in args)
        mod = "VOID" if ret is None else "RETURNS_VALUE"
        f = (f'<Function AccessType="default" StaticFunction="false">\n<ReturnModificator>{mod}</ReturnModificator>\n'
             f'<ReturnType>{cd(ret or "double")}</ReturnType>\n<Id>{self.model.ids()}</Id>\n<Name>{cd(name)}</Name>\n'
             + (f'<Description>{cd(doc)}</Description>\n' if doc else "")
             + f'<X>{x}</X><Y>{y}</Y>\n<Label><X>10</X><Y>0</Y></Label>\n<PublicFlag>false</PublicFlag>\n'
             f'<PresentationFlag>true</PresentationFlag>\n<ShowLabel>true</ShowLabel>\n{a}<Body>{cd(body)}</Body>\n</Function>')
        self.functions.append(f)
        sig = ", ".join(f"{t} {n}" for t, n in args)
        self.shadow.method(self.name, f"  {ret or 'void'} {name}({sig}) {{\n{body}\n  }}")

    # -- flowchart blocks
    def block(self, name, cls, x, y, types, **params):
        """params: python values -> converted: str code, ('unit', code, unitClass, unit), ('entity', AgentClass)."""
        types = (types,) if isinstance(types, str) else tuple(types)
        xmlp = {}
        for k, v in params.items():
            if v is None:
                continue
            if isinstance(v, tuple) and v[0] == "unit":
                _, code, ucls, unit = v
                xmlp[k] = (f'<Value Class="CodeUnitValue">\n<Code>{cd(code)}</Code>\n'
                           f'<Unit Class="{ucls}">{cd(unit)}</Unit>\n</Value>')
                self._shadow_param(cls, k, code, types, name)
            elif isinstance(v, tuple) and v[0] == "entity":
                xmlp[k] = self.model.entity_value(v[1])
            else:
                code = "true" if v is True else "false" if v is False else str(v)
                xmlp[k] = f'<Value Class="CodeValue">\n<Code>{cd(code)}</Code>\n</Value>'
                self._shadow_param(cls, k, code, types, name)
        unknown = set(xmlp) - set(PARAMS[cls])
        assert not unknown, (cls, unknown)
        b = Block(name, cls, x, y, types, xmlp)
        self.blocks.append(b)
        n = len(GENERIC_ID[cls])
        tt = list(types) + ["Agent"] * (n - len(types))
        jt = f"com.anylogic.libraries.processmodeling.{cls}<{', '.join(tt)}>"
        self.shadow.field(self.name, f"public {jt} {name};")
        return name

    def _shadow_param(self, cls, pname, code, types, bname):
        c = str(code).strip()
        if c.startswith("self.") or c in ("true", "false") or _re.fullmatch(r"-?\d+(\.\d+)?", c):
            return  # constants are not compiled
        kind, rtype, locs = code_sig(cls, pname, types)
        self.shadow.snippet(self.name, kind, rtype, locs, code, f"{bname}.{pname}")

    def connect(self, src, sport, dst, dport):
        self.connectors.append((src, sport, dst, dport))

    # -- presentation
    def shape(self, xml):
        self.shapes.append(xml)

    def code_check(self, rtype, code, where, locals_=()):
        self.shadow.snippet(self.name, "value", rtype, list(locals_), code, where)


class Model:
    def __init__(self, name, package, alp_version="8.9.7"):
        self.name, self.package, self.alp_version = name, package, alp_version
        self.ids = Ids()
        self.id = self.ids()
        self.shadow = Shadow(package)
        self.classes = []
        self.experiments = []
        self.run_config_id = self.ids()

    def agent(self, name, entity=True):
        a = AgentClass(self, name, entity)
        self.classes.append(a)
        return a

    def entity_value(self, ac: AgentClass):
        return (f'<Value Class="EntityCodeValue">\n<IsAgentEntity>true</IsAgentEntity>\n<EntityEmbeddedObject>\n'
                f'<Id>{self.ids()}</Id>\n<ActiveObjectClass>\n<PackageName>{cd(self.package)}</PackageName>\n'
                f'<ClassName>{cd(ac.name)}</ClassName>\n</ActiveObjectClass>\n<GenericParameterSubstitute>\n'
                f'<GenericParameterSubstituteReference>\n<PackageName>{cd(self.package)}</PackageName>\n'
                f'<ClassName>{cd(ac.name)}</ClassName>\n<ItemName>{cd(ac.generic_id)}</ItemName>\n'
                f'</GenericParameterSubstituteReference>\n</GenericParameterSubstitute>\n<Parameters>\n</Parameters>\n'
                f'<ReplicationFlag>true</ReplicationFlag>\n<Replication Class="CodeValue">\n<Code>{cd(100)}</Code>\n'
                f'</Replication>\n<CollectionType>ARRAY_LIST_BASED</CollectionType>\n'
                f'<InitialSpeedCode Class="CodeUnitValue">\n<Code>{cd(10)}</Code>\n'
                f'<Unit Class="SpeedUnits">{cd("MPS")}</Unit>\n</InitialSpeedCode>\n'
                f'<InitialLocationType>AT_ANIMATION_POSITION</InitialLocationType>\n'
                + _xyz_codes() +
                f'<InitializationType>SPECIFIED_NUMBER</InitializationType>\n<InitializationDatabaseTableQuery>\n'
                f'<TableReference>\n</TableReference>\n</InitializationDatabaseTableQuery>\n'
                f'<InitializationDatabaseType>ONE_AGENT_PER_DATABASE_RECORD</InitializationDatabaseType>\n'
                f'<QuantityColumn>\n</QuantityColumn>\n</EntityEmbeddedObject>\n</Value>')

    # ------------------------------------------------------------------ serialisation
    def xml(self):
        out = ['<?xml version="1.0" encoding="UTF-8"?>\n<!--\n*************************************************\n'
               '\t         AnyLogic Project File\n*************************************************\n-->\n'
               f'<AnyLogicWorkspace WorkspaceVersion="1.9" AnyLogicVersion="8.9.7.202505201325" AlpVersion="{self.alp_version}">\n'
               f'<Model>\n<Id>{self.id}</Id>\n<Name>{cd(self.name)}</Name>\n<EngineVersion>6</EngineVersion>\n'
               f'<JavaPackageName>{cd(self.package)}</JavaPackageName>\n<ModelTimeUnit>{cd("Second")}</ModelTimeUnit>\n'
               '<ActiveObjectClasses>\n']
        for c in self.classes:
            out.append(self._class_xml(c))
        out.append('</ActiveObjectClasses>\n'
                   '<DifferentialEquationsMethod>EULER</DifferentialEquationsMethod>\n'
                   '<MixedEquationsMethod>RK45_NEWTON</MixedEquationsMethod>\n'
                   '<AlgebraicEquationsMethod>MODIFIED_NEWTON</AlgebraicEquationsMethod>\n'
                   '<AbsoluteAccuracy>1.0E-5</AbsoluteAccuracy>\n<FixedTimeStep>0.01</FixedTimeStep>\n'
                   '<RelativeAccuracy>1.0E-5</RelativeAccuracy>\n<TimeAccuracy>1.0E-5</TimeAccuracy>\n'
                   '<Frame>\n<Width>1500</Width>\n<Height>900</Height>\n</Frame>\n'
                   '<Database>\n<Logging>false</Logging>\n<AutoExport>false</AutoExport>\n'
                   '<ShutdownCompact>false</ShutdownCompact>\n<ImportSettings>\n</ImportSettings>\n'
                   '<ExportSettings>\n</ExportSettings>\n</Database>\n')
        main = self.classes[0]
        out.append(f'<RunConfiguration ActiveObjectClassId="{main.id}">\n<Id>{self.run_config_id}</Id>\n'
                   f'<Name>{cd("RunConfiguration")}</Name>\n<MaximumMemory>512</MaximumMemory>\n'
                   '<ModelTimeProperties>\n<StopOption>' + cd("Stop at specified time") + '</StopOption>\n'
                   '<InitialDate>' + cd("1759708800000") + '</InitialDate>\n<InitialTime>' + cd("0.0") + '</InitialTime>\n'
                   '<FinalDate>' + cd("1759716000000") + '</FinalDate>\n<FinalTime>' + cd("7200.0") + '</FinalTime>\n'
                   '</ModelTimeProperties>\n<AnimationProperties>\n<StopNever>true</StopNever>\n'
                   '<ExecutionMode>realTimeScaled</ExecutionMode>\n<RealTimeScale>1.0</RealTimeScale>\n'
                   '<EnableZoomAndPanning>false</EnableZoomAndPanning>\n<EnableDeveloperPanel>false</EnableDeveloperPanel>\n'
                   '<ShowDeveloperPanelOnStart>false</ShowDeveloperPanelOnStart>\n</AnimationProperties>\n'
                   '<Inputs>\n</Inputs>\n<Outputs>\n</Outputs>\n</RunConfiguration>\n<Experiments>\n')
        out += self.experiments
        out.append('</Experiments>\n'
                   '<RequiredLibraryReference>\n<LibraryName>' + cd(PML) + '</LibraryName>\n'
                   '<VersionMajor>8</VersionMajor>\n<VersionMinor>0</VersionMinor>\n<VersionBuild>5</VersionBuild>\n'
                   '</RequiredLibraryReference>\n</Model>\n</AnyLogicWorkspace>\n')
        return "".join(out)

    def _class_xml(self, c: AgentClass):
        P = self.package
        s = [f'<ActiveObjectClass>\n<Id>{c.id}</Id>\n<Name>{cd(c.name)}</Name>\n']
        if c.additional:
            s.append(f'<AdditionalClassCode>{cd(c.additional)}</AdditionalClassCode>\n')
        if c.imports:
            s.append(f'<Import>{cd(c.imports)}</Import>\n')
        if c.startup:
            s.append(f'<StartupCode>{cd(c.startup)}</StartupCode>\n')
        if c.destroy:
            s.append(f'<DestroyCode>{cd(c.destroy)}</DestroyCode>\n')
        s.append(f'<Generic>false</Generic>\n<GenericParameter>\n<Id>{c.generic_id}</Id>\n'
                 f'<Name>{cd(c.generic_id)}</Name>\n<GenericParameterValue Class="CodeValue">\n'
                 f'<Code>{cd("T extends Agent")}</Code>\n</GenericParameterValue>\n'
                 f'<GenericParameterLabel>{cd("Generic parameter:")}</GenericParameterLabel>\n</GenericParameter>\n'
                 f'<FlowChartsUsage>ENTITY</FlowChartsUsage>\n<SamplesToKeep>100</SamplesToKeep>\n'
                 f'<LimitNumberOfArrayElements>false</LimitNumberOfArrayElements>\n<ElementsLimitValue>100</ElementsLimitValue>\n'
                 f'<MakeDefaultViewArea>true</MakeDefaultViewArea>\n<SceneGridColor/>\n<SceneBackgroundColor/>\n'
                 f'<SceneSkybox>null</SceneSkybox>\n' + _AGENT_PROPS +
                 f'<ScaleRuler>\n<Id>{c.scale_id}</Id>\n<Name>{cd("scale")}</Name>\n<X>0</X><Y>-150</Y>\n'
                 '<PublicFlag>false</PublicFlag>\n<PresentationFlag>false</PresentationFlag>\n<ShowLabel>false</ShowLabel>\n'
                 '<DrawMode>SHAPE_DRAW_2D3D</DrawMode>\n<Length>100</Length>\n<Rotation>0</Rotation>\n'
                 '<ScaleType>BASED_ON_LENGTH</ScaleType>\n<ModelLength>10</ModelLength>\n<LengthUnits>METER</LengthUnits>\n'
                 '<Scale>10</Scale>\n<InheritedFromParentAgentType>true</InheritedFromParentAgentType>\n</ScaleRuler>\n'
                 f'<CurrentLevel>{c.level_id}</CurrentLevel>\n<ConnectionsId>{c.links_id}</ConnectionsId>\n')
        if c.variables:
            s.append("<Variables>\n" + "\n".join(c.variables) + "\n</Variables>\n")
        if c.connectors:
            s.append("<Connectors>\n")
            byname = {b.name: b for b in c.blocks}
            for i, (src, sp, dst, dp) in enumerate(c.connectors):
                a, b = byname[src], byname[dst]
                x0, y0 = a.x + 10, a.y
                x1, y1 = b.x - 10, b.y
                s.append(f'<Connector>\n<Id>{self.ids()}</Id>\n<Name>{cd(f"connector{i}")}</Name>\n'
                         f'<X>{x0}</X><Y>{y0}</Y>\n<Label><X>10</X><Y>0</Y></Label>\n<PublicFlag>false</PublicFlag>\n'
                         f'<PresentationFlag>true</PresentationFlag>\n<ShowLabel>false</ShowLabel>\n'
                         f'<SourceEmbeddedObjectReference>\n<PackageName>{cd(P)}</PackageName>\n<ClassName>{cd(c.name)}</ClassName>\n'
                         f'<ItemName>{cd(src)}</ItemName>\n</SourceEmbeddedObjectReference>\n'
                         f'<SourceConnectableItemReference>\n<PackageName>{cd(PML)}</PackageName>\n<ClassName>{cd(a.cls)}</ClassName>\n'
                         f'<ItemName>{cd(sp)}</ItemName>\n</SourceConnectableItemReference>\n'
                         f'<TargetEmbeddedObjectReference>\n<PackageName>{cd(P)}</PackageName>\n<ClassName>{cd(c.name)}</ClassName>\n'
                         f'<ItemName>{cd(dst)}</ItemName>\n</TargetEmbeddedObjectReference>\n'
                         f'<TargetConnectableItemReference>\n<PackageName>{cd(PML)}</PackageName>\n<ClassName>{cd(b.cls)}</ClassName>\n'
                         f'<ItemName>{cd(dp)}</ItemName>\n</TargetConnectableItemReference>\n'
                         f'<Points>\n<Point><X>0</X><Y>0</Y></Point>\n<Point><X>{x1 - x0}</X><Y>{y1 - y0}</Y></Point>\n</Points>\n</Connector>\n')
            s.append("</Connectors>\n")
        if c.functions:
            s.append("<Functions>\n" + "\n".join(c.functions) + "\n</Functions>\n")
        s.append(f'<AgentLinks>\n<AgentLink>\n<Id>{c.links_id}</Id>\n<Name>{cd("connections")}</Name>\n'
                 '<X>50</X><Y>-50</Y>\n<Label><X>15</X><Y>0</Y></Label>\n<PublicFlag>false</PublicFlag>\n'
                 '<PresentationFlag>true</PresentationFlag>\n<ShowLabel>true</ShowLabel>\n'
                 '<HandleReceiveInConnections>false</HandleReceiveInConnections>\n<AgentLinkType>COLLECTION_OF_LINKS</AgentLinkType>\n'
                 f'<AgentLinkBidirectional>true</AgentLinkBidirectional>\n<MessageType>{cd("Object")}</MessageType>\n'
                 '<LineStyle>SOLID</LineStyle>\n<LineWidth>1</LineWidth>\n<LineColor>-16777216</LineColor>\n'
                 '<LineZOrder>UNDER_AGENTS</LineZOrder>\n<LineArrow>NONE</LineArrow>\n<LineArrowPosition>END</LineArrowPosition>\n'
                 '</AgentLink>\n</AgentLinks>\n')
        if c.blocks:
            s.append("<EmbeddedObjects>\n")
            for b in c.blocks:
                s.append(self._block_xml(c, b))
            s.append("</EmbeddedObjects>\n")
        # presentation: one level holding shapes, markup and a network with paths
        s.append(f'<Presentation>\n<Level>\n<Id>{c.level_id}</Id>\n<Name>{cd("level")}</Name>\n<X>0</X><Y>0</Y>\n'
                 '<Label><X>10</X><Y>0</Y></Label>\n<PublicFlag>true</PublicFlag>\n<PresentationFlag>true</PresentationFlag>\n'
                 '<ShowLabel>false</ShowLabel>\n<DrawMode>SHAPE_DRAW_2D3D</DrawMode>\n<Z>0</Z>\n'
                 '<LevelVisibility>ALWAYS_SHOW</LevelVisibility>\n')
        inner = list(c.markup_level) + list(c.shapes)
        if c.network_paths:
            inner.append(f'<Network>\n<Id>{self.ids()}</Id>\n<Name>{cd("network")}</Name>\n<X>0</X><Y>0</Y>\n'
                         '<Label><X>10</X><Y>0</Y></Label>\n<PublicFlag>true</PublicFlag>\n<PresentationFlag>true</PresentationFlag>\n'
                         '<ShowLabel>false</ShowLabel>\n<DrawMode>SHAPE_DRAW_2D3D</DrawMode>\n'
                         '<Presentation>\n' + "\n".join(c.network_paths) + '\n</Presentation>\n<Z>0</Z>\n</Network>')
        if inner:
            s.append("<Presentation>\n" + "\n".join(inner) + "\n</Presentation>\n")
        s.append('</Level>\n</Presentation>\n</ActiveObjectClass>\n')
        return "".join(s)

    def _block_xml(self, c, b: Block):
        P = self.package
        gps = []
        for gid, t in zip(GENERIC_ID[b.cls], b.types):
            gps.append(f'<GenericParameterSubstitute>\n<GenericParameterSubstituteReference>\n'
                       f'<PackageName>{cd(PML)}</PackageName>\n<ClassName>{cd(b.cls)}</ClassName>\n'
                       f'<ItemName>{cd(gid)}</ItemName>\n</GenericParameterSubstituteReference>\n'
                       f'<GenericParameterSubstituteValue Class="CodeValue">\n<Code>{cd(t)}</Code>\n'
                       f'</GenericParameterSubstituteValue>\n</GenericParameterSubstitute>\n')
        params = []
        for pn in PARAMS[b.cls]:
            if pn in b.params:
                params.append(f'<Parameter>\n<Name>{cd(pn)}</Name>\n{b.params[pn]}\n</Parameter>\n')
            else:
                params.append(f'<Parameter>\n<Name>{cd(pn)}</Name>\n</Parameter>\n')
        return (f'<EmbeddedObject>\n<Id>{self.ids()}</Id>\n<Name>{cd(b.name)}</Name>\n<X>{b.x}</X><Y>{b.y}</Y>\n'
                '<Label><X>-10</X><Y>-20</Y></Label>\n<PublicFlag>false</PublicFlag>\n<PresentationFlag>true</PresentationFlag>\n'
                f'<ShowLabel>true</ShowLabel>\n<ActiveObjectClass>\n<PackageName>{cd(PML)}</PackageName>\n'
                f'<ClassName>{cd(b.cls)}</ClassName>\n</ActiveObjectClass>\n' + "".join(gps) +
                '<Parameters>\n' + "".join(params) + '</Parameters>\n'
                '<ReplicationFlag>false</ReplicationFlag>\n<Replication Class="CodeValue">\n<Code>' + cd(100) + '</Code>\n</Replication>\n'
                '<CollectionType>ARRAY_LIST_BASED</CollectionType>\n<InitialSpeedCode Class="CodeUnitValue">\n'
                f'<Code>{cd(10)}</Code>\n<Unit Class="SpeedUnits">{cd("MPS")}</Unit>\n</InitialSpeedCode>\n'
                '<InitialLocationType>AT_ANIMATION_POSITION</InitialLocationType>\n' + _xyz_codes() +
                '<InitializationType>SPECIFIED_NUMBER</InitializationType>\n<InitializationDatabaseTableQuery>\n'
                '<TableReference>\n</TableReference>\n</InitializationDatabaseTableQuery>\n'
                '<InitializationDatabaseType>ONE_AGENT_PER_DATABASE_RECORD</InitializationDatabaseType>\n'
                '<QuantityColumn>\n</QuantityColumn>\n</EmbeddedObject>\n')


def _xyz_codes():
    out = ""
    for tag, v in (("XCode", "0"), ("YCode", "0"), ("ZCode", "0"), ("ColumnCode", "0"), ("RowCode", "0"),
                   ("LatitudeCode", "0"), ("LongitudeCode", "0"), ("LocationNameCode", '""')):
        out += f'<{tag} Class="CodeValue">\n<Code>{cd(v)}</Code>\n</{tag}>\n'
    return out


_AGENT_PROPS = (
    '<AgentProperties>\n<EnvironmentDefinesInitialLocation>true</EnvironmentDefinesInitialLocation>\n'
    '<RotateAnimationTowardsMovement>true</RotateAnimationTowardsMovement>\n<RotateAnimationVertically>false</RotateAnimationVertically>\n'
    f'<VelocityCode Class="CodeUnitValue">\n<Code>{cd(10)}</Code>\n<Unit Class="SpeedUnits">{cd("MPS")}</Unit>\n</VelocityCode>\n'
    f'<PhysicalLength Class="CodeUnitValue">\n<Code>{cd(1)}</Code>\n<Unit Class="LengthUnits">{cd("METER")}</Unit>\n</PhysicalLength>\n'
    f'<PhysicalWidth Class="CodeUnitValue">\n<Code>{cd(1)}</Code>\n<Unit Class="LengthUnits">{cd("METER")}</Unit>\n</PhysicalWidth>\n'
    f'<PhysicalHeight Class="CodeUnitValue">\n<Code>{cd(1)}</Code>\n<Unit Class="LengthUnits">{cd("METER")}</Unit>\n</PhysicalHeight>\n'
    '</AgentProperties>\n<EnvironmentProperties>\n<EnableSteps>false</EnableSteps>\n'
    f'<StepDurationCode Class="CodeUnitValue">\n<Code>{cd("1.0")}</Code>\n<Unit Class="TimeUnits">{cd("SECOND")}</Unit>\n</StepDurationCode>\n'
    f'<SpaceType>CONTINUOUS</SpaceType>\n<WidthCode>{cd(500)}</WidthCode>\n<HeightCode>{cd(500)}</HeightCode>\n'
    f'<ZHeightCode>{cd(0)}</ZHeightCode>\n<ColumnsCountCode>{cd(100)}</ColumnsCountCode>\n<RowsCountCode>{cd(100)}</RowsCountCode>\n'
    '<NeigborhoodType>MOORE</NeigborhoodType>\n<LayoutType>USER_DEF</LayoutType>\n<LayoutTypeApplyOnStartup>true</LayoutTypeApplyOnStartup>\n'
    '<NetworkType>USER_DEF</NetworkType>\n<NetworkTypeApplyOnStartup>true</NetworkTypeApplyOnStartup>\n'
    f'<ConnectionsPerAgentCode>{cd(2)}</ConnectionsPerAgentCode>\n<ConnectionsRangeCode>{cd(50)}</ConnectionsRangeCode>\n'
    f'<NeighborLinkFractionCode>{cd(0.95)}</NeighborLinkFractionCode>\n<MCode>{cd(10)}</MCode>\n</EnvironmentProperties>\n'
    '<DatasetsCreationProperties>\n<AutoCreate>false</AutoCreate>\n<OccurrenceAtTime>true</OccurrenceAtTime>\n'
    '<OccurrenceDate>1759708800000</OccurrenceDate>\n'
    f'<OccurrenceTime Class="CodeUnitValue">\n<Code>{cd(0)}</Code>\n<Unit Class="TimeUnits">{cd("SECOND")}</Unit>\n</OccurrenceTime>\n'
    f'<RecurrenceCode Class="CodeUnitValue">\n<Code>{cd(1)}</Code>\n<Unit Class="TimeUnits">{cd("SECOND")}</Unit>\n</RecurrenceCode>\n'
    '</DatasetsCreationProperties>\n')


# ----------------------------------------------------------------------------- shapes
class Shapes:
    """Shape XML builders. Every dynamic code expression is also compile-checked."""

    def __init__(self, ac: AgentClass):
        self.ac = ac
        self.ids = ac.model.ids
        self.n = itertools.count(1)

    def _head(self, kind, name, x, y, dyn, draw="SHAPE_DRAW_2D"):
        name = name or f"{kind.lower()}{next(self.n)}"
        x, y = (int(v) if float(v).is_integer() else v for v in (x, y))
        s = (f'<{kind}>\n<Id>{self.ids()}</Id>\n<Name>{cd(name)}</Name>\n<X>{x}</X><Y>{y}</Y>\n'
             '<Label><X>10</X><Y>0</Y></Label>\n<PublicFlag>true</PublicFlag>\n<PresentationFlag>true</PresentationFlag>\n'
             f'<ShowLabel>false</ShowLabel>\n<DrawMode>{draw}</DrawMode>\n')
        locs = [("int", "index")] if dyn.get("rep") else []
        for tag, rt in (("XCode", "double"), ("YCode", "double"), ("VisibleCode", "boolean")):
            if dyn.get(tag):
                s += f'<{tag}>{cd(dyn[tag])}</{tag}>\n'
                self.ac.code_check(rt, dyn[tag], f"{name}.{tag}", locs)
        if dyn.get("rep"):
            s += f'<ReplicationCode Class="CodeValue">\n<Code>{cd(dyn["rep"])}</Code>\n</ReplicationCode>\n'
            self.ac.code_check("int", dyn["rep"], f"{name}.replication")
        s += '<EmbeddedIcon>false</EmbeddedIcon>\n<Z>0</Z>\n'
        return s, locs, name

    def rect(self, x, y, w, h, fill="#FFFFFF", line="#5B6B7F", lw=1, name=None, **dyn):
        s, locs, name = self._head("Rectangle", name, x, y, dyn)
        s += (f'<ZHeight>10</ZHeight>\n<LineWidth>{lw}</LineWidth>\n'
              + (f'<LineColor>{color(line)}</LineColor>\n' if line else '<LineColor/>\n')
              + '<LineMaterial>null</LineMaterial>\n<LineStyle>SOLID</LineStyle>\n'
              f'<Width>{w}</Width>\n<Height>{h}</Height>\n')
        for tag in ("WidthCode", "HeightCode"):
            if dyn.get(tag):
                s += f'<{tag}>{cd(dyn[tag])}</{tag}>\n'
                self.ac.code_check("double", dyn[tag], f"{name}.{tag}", locs)
        s += '<Rotation>0.0</Rotation>\n' + (f'<FillColor>{color(fill)}</FillColor>\n' if fill else '<FillColor/>\n')
        if dyn.get("FillColorCode"):
            s += f'<FillColorCode>{cd(dyn["FillColorCode"])}</FillColorCode>\n'
            self.ac.code_check("Color", dyn["FillColorCode"], f"{name}.FillColorCode", locs)
        s += '<FillMaterial>null</FillMaterial>\n</Rectangle>'
        self.ac.shape(s)

    def oval(self, x, y, r, fill="#9E9E9E", line="#333333", name=None, **dyn):
        s, locs, name = self._head("Oval", name, x, y, dyn)
        s += (f'<ZHeight>10</ZHeight>\n<LineWidth>1</LineWidth>\n<LineColor>{color(line)}</LineColor>\n'
              '<LineMaterial>null</LineMaterial>\n<LineStyle>SOLID</LineStyle>\n'
              f'<RadiusX>{r}</RadiusX>\n<RadiusY>{r}</RadiusY>\n<Rotation>0.0</Rotation>\n<FillColor>{color(fill)}</FillColor>\n')
        if dyn.get("FillColorCode"):
            s += f'<FillColorCode>{cd(dyn["FillColorCode"])}</FillColorCode>\n'
            self.ac.code_check("Color", dyn["FillColorCode"], f"{name}.FillColorCode", locs)
        s += '<FillMaterial>null</FillMaterial>\n</Oval>'
        self.ac.shape(s)

    def text(self, x, y, txt, size=12, bold=False, col="#263238", align="LEFT", name=None, **dyn):
        s, locs, name = self._head("Text", name, x, y, dyn, draw="SHAPE_DRAW_2D3D")
        s += f'<Rotation>0.0</Rotation>\n<Color>{color(col)}</Color>\n'
        if dyn.get("ColorCode"):
            s += f'<ColorCode>{cd(dyn["ColorCode"])}</ColorCode>\n'
            self.ac.code_check("Color", dyn["ColorCode"], f"{name}.ColorCode", locs)
        s += f'<Text>{cd(txt)}</Text>\n'
        if dyn.get("TextCode"):
            s += f'<TextCode>{cd(dyn["TextCode"])}</TextCode>\n'
            self.ac.code_check("Object", dyn["TextCode"], f"{name}.TextCode", locs)
        s += (f'<Font>\n<Name>SansSerif</Name>\n<Size>{size}</Size>\n<Style>{1 if bold else 0}</Style>\n</Font>\n'
              f'<Alignment>{align}</Alignment>\n</Text>')
        self.ac.shape(s)

    def line(self, x, y, dx, dy, col="#90A4AE", lw=1, style="SOLID", name=None, **dyn):
        s, locs, name = self._head("Line", name, x, y, dyn)
        s += (f'<ZHeight>10</ZHeight>\n<LineWidth>{lw}</LineWidth>\n<LineColor>{color(col)}</LineColor>\n'
              f'<LineMaterial>null</LineMaterial>\n<LineStyle>{style}</LineStyle>\n<BeginArrowSize>1</BeginArrowSize>\n'
              '<BeginArrowStyle>0</BeginArrowStyle>\n<EndArrowSize>1</EndArrowSize>\n<EndArrowStyle>0</EndArrowStyle>\n'
              f'<Dx>{dx}</Dx>\n<Dy>{dy}</Dy>\n<Dz>0</Dz>\n</Line>')
        self.ac.shape(s)

    def arrow(self, x, y, dx, dy, col="#90A4AE", lw=2, name=None):
        s, locs, name = self._head("Line", name, x, y, {})
        s += (f'<ZHeight>10</ZHeight>\n<LineWidth>{lw}</LineWidth>\n<LineColor>{color(col)}</LineColor>\n'
              '<LineMaterial>null</LineMaterial>\n<LineStyle>SOLID</LineStyle>\n<BeginArrowSize>1</BeginArrowSize>\n'
              '<BeginArrowStyle>0</BeginArrowStyle>\n<EndArrowSize>2</EndArrowSize>\n<EndArrowStyle>1</EndArrowStyle>\n'
              f'<Dx>{dx}</Dx>\n<Dy>{dy}</Dy>\n<Dz>0</Dz>\n</Line>')
        self.ac.shape(s)

    # -- markup
    def point_node(self, name, x, y, col="#1E88E5"):
        self.ac.markup_level.append(
            f'<PointNode>\n<Id>{self.ids()}</Id>\n<Name>{cd(name)}</Name>\n<X>{x}</X><Y>{y}</Y>\n'
            '<Label><X>10</X><Y>0</Y></Label>\n<PublicFlag>true</PublicFlag>\n<PresentationFlag>true</PresentationFlag>\n'
            '<ShowLabel>false</ShowLabel>\n<DrawMode>SHAPE_DRAW_2D3D</DrawMode>\n<Z>0</Z>\n<FakeNode>false</FakeNode>\n'
            f'<Lock>false</Lock>\n<Color>{color(col)}</Color>\n<Radius>1</Radius>\n<SpeedLimit>false</SpeedLimit>\n'
            f'<SpeedLimitValue Class="UnitValue">\n<Value Class="Double">10</Value>\n<Unit Class="SpeedUnits">{cd("MPS")}</Unit>\n'
            '</SpeedLimitValue>\n</PointNode>')
        self.ac.shadow.field(self.ac.name, f"public PointNode {name};")

    def path(self, name, x, y, pts, col="#90A4AE"):
        """pts: list of (dx, dy) vertices relative to (x, y); straight segments."""
        p = []
        for i, (px, py) in enumerate(pts):
            prv = pts[i - 1] if i > 0 else None
            nxt = pts[i + 1] if i + 1 < len(pts) else None
            # control points on the segments (straight path): 1/3 towards neighbours
            cin = (px + (prv[0] - px) / 3, py + (prv[1] - py) / 3) if prv else (px - (nxt[0] - px) / 3, py - (nxt[1] - py) / 3)
            cout = (px + (nxt[0] - px) / 3, py + (nxt[1] - py) / 3) if nxt else (px + (px - prv[0]) / 3, py + (py - prv[1]) / 3)
            for (qx, qy) in ((px, py), cin, cout):
                p.append(f'<Point><X>{qx:g}</X><Y>{qy:g}</Y><Z>0</Z></Point>')
        self.ac.network_paths.append(
            f'<Path>\n<Id>{self.ids()}</Id>\n<Name>{cd(name)}</Name>\n<X>{x}</X><Y>{y}</Y>\n'
            '<Label><X>10</X><Y>0</Y></Label>\n<PublicFlag>true</PublicFlag>\n<PresentationFlag>true</PresentationFlag>\n'
            '<ShowLabel>false</ShowLabel>\n<DrawMode>SHAPE_DRAW_2D3D</DrawMode>\n<Z>0</Z>\n'
            f'<LineColor>{color(col)}</LineColor>\n<LineMaterial>null</LineMaterial>\n<LineWidth>1</LineWidth>\n'
            '<PathType>dashedLine</PathType>\n'
            f'<Width Class="UnitValue">\n<Value Class="Double">1</Value>\n<Unit Class="LengthUnits">{cd("METER")}</Unit>\n</Width>\n'
            '<Points>\n' + "\n".join(p) + '\n</Points>\n<Bidirectional>true</Bidirectional>\n<SpeedLimit>false</SpeedLimit>\n'
            f'<SpeedLimitValue Class="CodeUnitValue">\n<Code>{cd("10.0")}</Code>\n<Unit Class="SpeedUnits">{cd("MPS")}</Unit>\n'
            '</SpeedLimitValue>\n<LimitNumberOfTransporters>false</LimitNumberOfTransporters>\n'
            '<LimitNumberOfTransportersValue>10</LimitNumberOfTransportersValue>\n</Path>')
        self.ac.shadow.field(self.ac.name, f"public Path {name};")

    def time_plot(self, name, x, y, w, h, series, window=7200, recurrence=60, vmax=None):
        """series: list of (title, expression, '#color')."""
        ds = []
        for title, expr, col in series:
            self.ac.code_check("double", expr, f"{name}.{title}")
            ds.append(f'<DatasetExpression>\n<Title>{cd(title)}</Title>\n<Id>{self.ids()}</Id>\n'
                      f'<Expression>{cd("_ds_" + name + str(len(ds)))}</Expression>\n<Color>{color(col)}</Color>\n'
                      f'<Expression2>{cd(expr)}</Expression2>\n<Expression2Flag>true</Expression2Flag>\n'
                      '<PointStyle>NONE</PointStyle>\n<LineWidth>2.0</LineWidth>\n</DatasetExpression>\n')
        vs = ("FIXED", 0, vmax) if vmax else ("AUTO", 0, 1)
        self.ac.shape(
            f'<TimePlot>\n<Id>{self.ids()}</Id>\n<Name>{cd(name)}</Name>\n<X>{x}</X><Y>{y}</Y>\n'
            '<Label><X>0</X><Y>-10</Y></Label>\n<PublicFlag>true</PublicFlag>\n<PresentationFlag>true</PresentationFlag>\n'
            '<ShowLabel>false</ShowLabel>\n<DrawMode>SHAPE_DRAW_2D3D</DrawMode>\n<AutoUpdate>true</AutoUpdate>\n'
            f'<RecurrenceProperties>\n<Id>{self.ids()}</Id>\n'
            '<OccurrenceAtTime>true</OccurrenceAtTime>\n<OccurrenceDate>1759708800000</OccurrenceDate>\n'
            f'<OccurrenceTime Class="CodeUnitValue">\n<Code>{cd(0)}</Code>\n<Unit Class="TimeUnits">{cd("SECOND")}</Unit>\n</OccurrenceTime>\n'
            f'<RecurrenceCode Class="CodeUnitValue">\n<Code>{cd(recurrence)}</Code>\n<Unit Class="TimeUnits">{cd("SECOND")}</Unit>\n</RecurrenceCode>\n'
            '</RecurrenceProperties>\n'
            f'<EmbeddedIcon>false</EmbeddedIcon>\n<Width>{w}</Width>\n<Height>{h}</Height>\n<BackgroundColor/>\n<BorderColor/>\n'
            f'<ChartArea>\n<XOffset>50</XOffset>\n<YOffset>20</YOffset>\n<Width>{w - 70}</Width>\n<Height>{h - 80}</Height>\n'
            '<BackgroundColor>-1</BackgroundColor>\n<BorderColor>-16777216</BorderColor>\n<GridColor>-3355444</GridColor>\n</ChartArea>\n'
            '<Legend>\n<Place>SOUTH</Place>\n<TextColor>-16777216</TextColor>\n<Size>30</Size>\n</Legend>\n'
            '<Labels>\n<HorLabelsPosition>DEFAULT</HorLabelsPosition>\n<VerLabelsPosition>DEFAULT</VerLabelsPosition>\n'
            '<TextColor>-12566464</TextColor>\n</Labels>\n<ShowLegend>true</ShowLegend>\n'
            '<TimeWindowsMovementType>MOVEMENT_WITH_DATA</TimeWindowsMovementType>\n<TimeWindowUnits>MODEL_TIME_UNIT</TimeWindowUnits>\n'
            f'<VerScaleFromExpression>{cd(vs[1])}</VerScaleFromExpression>\n<VerScaleToExpression>{cd(vs[2])}</VerScaleToExpression>\n'
            f'<VerScaleType>{vs[0]}</VerScaleType>\n<DrawLine>true</DrawLine>\n<Interpolation>LINEAR</Interpolation>\n'
            + "".join(ds) +
            f'<SamplesToKeep>{int(window / recurrence) + 5}</SamplesToKeep>\n<TimeWindowExpression>{cd(window)}</TimeWindowExpression>\n'
            '<FillAreaUnderLine>false</FillAreaUnderLine>\n<LabelFormat>MODEL_TIME_UNITS</LabelFormat>\n</TimePlot>')
