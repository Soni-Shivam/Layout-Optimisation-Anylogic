"""Extracts block parameter definitions from the Process Modeling Library (library.xml inside
ProcessModelingLibrary.jar of the local AnyLogic install) -> tools/pml_spec.json"""
import json, pathlib, re, zipfile, os
AL = os.environ.get("AL_PLUGINS", os.path.expanduser("~/AnyLogic/anylogic/plugins"))
JAR = next(pathlib.Path(AL).glob("com.anylogic.process_modeling_library_*")) / "lib" / "ProcessModelingLibrary.jar"
s = zipfile.ZipFile(JAR).read("library.xml").decode("utf-8")
spec = {}
for cls in ["Source", "Sink", "Queue", "Delay", "Seize", "Release", "Service", "SelectOutput", "Pickup", "Combine",
            "Assembler", "RestrictedAreaStart", "RestrictedAreaEnd", "ResourcePool", "Enter", "Wait"]:
    m = re.search(r'<ActiveObjectClass>\s*<Id>\d+</Id>\s*<Name><!\[CDATA\[' + cls + r'\]\]></Name>(.*?)\n\t\t</ActiveObjectClass>', s, re.S)
    body = m.group(1)
    gens = re.findall(r'<GenericParameter>\s*<Id>(\d+)</Id>.*?<Code><!\[CDATA\[(\w+) extends', body, re.S)
    params = []
    for v in re.finditer(r'<Variable Class="Parameter">\s*<Id>\d+</Id>\s*<Name><!\[CDATA\[(\w+)\]\]></Name>(.*?)</Variable>', body, re.S):
        name, b = v.groups()
        props = re.search(r'<Properties[^>]*ModificatorType="(\w+)"', b)
        typ = re.search(r'<Type><!\[CDATA\[(.*?)\]\]></Type>', b).group(1)
        unit = re.search(r'<UnitType><!\[CDATA\[(.*?)\]\]></UnitType>', b)
        args = re.findall(r'<MethodArgument>\s*<Name><!\[CDATA\[(\w+)\]\]></Name>\s*<Type><!\[CDATA\[(.*?)\]\]></Type>', b)
        params.append(dict(name=name, kind=props.group(1) if props else "STATIC", type=typ,
                           unit=unit.group(1) if unit else "NONE", args=args))
    spec[cls] = dict(generics=gens, params=params)
    print(cls, [g[1] for g in gens], len(params))
(pathlib.Path(__file__).parent / "pml_spec.json").write_text(json.dumps(spec, indent=1))
