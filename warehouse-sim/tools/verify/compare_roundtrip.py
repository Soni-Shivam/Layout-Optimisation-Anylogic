"""Compares a generated .alp with the copy re-written by AnyLogic's own serializer."""
import sys, re, collections
import xml.etree.ElementTree as ET

def load(path):
    t = ET.parse(path).getroot()
    out = collections.OrderedDict()
    for cls in t.iter("ActiveObjectClass"):
        nm = cls.findtext("Name")
        if nm is None or cls.find("Id") is None:
            continue
        d = out.setdefault(nm, {})
        for eo in cls.findall("./EmbeddedObjects/EmbeddedObject"):
            params = {}
            for p in eo.findall("./Parameters/Parameter"):
                v = p.find("Value")
                if v is not None:
                    code = v.findtext("Code")
                    if code is None and v.get("Class") == "EntityCodeValue":
                        code = "entity:" + (v.findtext("./EntityEmbeddedObject/ActiveObjectClass/ClassName") or "")
                    params[p.findtext("Name")] = (code or "").strip()
            gps = [g.findtext("./GenericParameterSubstituteValue/Code") for g in eo.findall("GenericParameterSubstitute")]
            d["block:" + eo.findtext("Name")] = (eo.findtext("./ActiveObjectClass/ClassName"), tuple(gps), params)
        for c in cls.findall("./Connectors/Connector"):
            key = (c.findtext("./SourceEmbeddedObjectReference/ItemName"), c.findtext("./SourceConnectableItemReference/ItemName"),
                   c.findtext("./TargetEmbeddedObjectReference/ItemName"), c.findtext("./TargetConnectableItemReference/ItemName"))
            d.setdefault("connectors", set()).add(key)
        for v in cls.findall("./Variables/Variable"):
            d["var:" + v.findtext("Name")] = (v.get("Class"), v.findtext("./Properties/Type"),
                                             (v.findtext("./Properties/InitialValue/Code") or v.findtext("./Properties/DefaultValue/Code") or "").strip())
        for f in cls.findall("./Functions/Function"):
            d["fn:" + f.findtext("Name")] = (f.findtext("ReturnModificator"), f.findtext("ReturnType"),
                                            tuple((p.findtext("Name"), p.findtext("Type")) for p in f.findall("Parameter")),
                                            f.findtext("Body").strip())
        for tag in ("StartupCode", "AdditionalClassCode", "Import"):
            if cls.findtext(tag):
                d[tag] = cls.findtext(tag).strip()
        lvl = cls.find("./Presentation/Level")
        if lvl is not None:
            for sh in lvl.iter():
                if sh.tag in ("Rectangle", "Oval", "Text", "Line", "PointNode", "Path", "TimePlot") and sh.findtext("Name"):
                    codes = {c.tag: (c.text or "").strip() for c in sh if c.tag.endswith("Code") and c.tag != "Code"}
                    rep = sh.findtext("./ReplicationCode/Code")
                    pts = tuple((p.findtext("X"), p.findtext("Y")) for p in sh.findall("./Points/Point"))
                    ds = tuple((e.findtext("Title"), e.findtext("Expression2")) for e in sh.findall("DatasetExpression"))
                    d[f"shape:{sh.tag}:{sh.findtext('Name')}"] = (codes, rep, sh.findtext("X"), sh.findtext("Y"),
                                                                   sh.findtext("Text"), len(pts), ds)
    ex = {}
    for e in t.find("./Model/Experiments"):
        ex[e.findtext("Name")] = (e.tag, (e.findtext("AfterSimulationRunCode") or "").strip(), e.findtext("NumberOfRuns"),
                                  [(r.findtext("Id"), r.findtext("Type"), r.findtext("./From/Code"), r.findtext("./To/Code"))
                                   for r in e.findall("RangeVariationParamValue")],
                                  e.findtext("./ReplicationsProperties/UseReplication"),
                                  e.findtext("./ReplicationsProperties/ReplicationPerIteration"),
                                  e.findtext("./ModelTimeProperties/FinalTime"))
    out["__experiments__"] = ex
    return out

a, b = load(sys.argv[1]), load(sys.argv[2])
problems = 0
for cls in a:
    if cls not in b:
        print("MISSING CLASS", cls); problems += 1; continue
    for k, v in a[cls].items():
        w = b[cls].get(k)
        if w != v:
            problems += 1
            print(f"DIFF {cls} {k}\n   gen: {str(v)[:400]}\n   rt : {str(w)[:400]}")
    for k in b[cls]:
        if k not in a[cls]:
            print(f"EXTRA in round trip {cls} {k}")
counts = {c: collections.Counter(k.split(':')[0] for k in a[c]) for c in a if c != "__experiments__"}
print("counts:", {c: dict(v) for c, v in counts.items()})
print("connectors:", {c: len(a[c].get("connectors", ())) for c in a if c != "__experiments__"})
print("PROBLEMS:", problems)
