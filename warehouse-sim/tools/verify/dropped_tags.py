"""Lists XML element paths present in the generated .alp but absent after AnyLogic's round trip
(= things the AnyLogic loader ignored)."""
import sys, collections
import xml.etree.ElementTree as ET

def paths(path):
    root = ET.parse(path).getroot()
    out = collections.Counter()
    def walk(e, pre):
        p = pre + "/" + e.tag
        out[p] += 1
        for c in e:
            walk(c, p)
    walk(root, "")
    return out

a, b = paths(sys.argv[1]), paths(sys.argv[2])
for p in sorted(a):
    if p not in b:
        print("DROPPED", a[p], p)
    elif b[p] < a[p]:
        print(f"FEWER  {a[p]} -> {b[p]}", p)
