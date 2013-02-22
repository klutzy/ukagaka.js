class Surface(object):
    def __init__(self, path):
        self.path = path
        self.collisions = []
        self.animations = {}
        self.elements = []

    def __str__(self):
        ret = "elements: " + str(self.elements) + "\n"
        ret += "animations: " + str(self.animations) + "\n"

        return ret


def parse_blob(text):
    title = None
    blob = []
    is_blob = False
    for line in text.splitlines():
        line = line.strip()
        if line == '{':
            is_blob = True
        elif line == '}':
            is_blob = False
            yield (title, blob)
            title = None
            blob = []
        elif is_blob:
            blob.append(line)
        else:
            if not line:
                continue
            title = line


def parse_surface(blob, path):
    surface = Surface(path)
    for cmd in blob:
        cmd = cmd.split(',')
        c = cmd[0]
        if c.startswith('collision'):
            surface.collisions.append(cmd)
        elif c.startswith('animation'):
            a = c.split('.')
            if a[0] not in surface.animations:
                surface.animations[a[0]] = []
            surface.animations[a[0]].append([a[1]] + cmd[1:])
        elif c.startswith('element'):
            surface.elements.append(cmd)

    return surface


def parse(text, path):
    if not text:
        raise ValueError("no text")
    ret = []
    for title, blob in parse_blob(text):
        if title == 'descript':
            continue
        if title.startswith('surface'):
            surface = parse_surface(blob, path)
            ret.append(surface)

    return ret


def main():
    import sys
    path = './master'
    if len(sys.argv) > 1:
        path = sys.argv[1]
    fn = path + '/surfaces.txt'
    p = parse(open(fn).read(), path)

    print(p[0])
    return p

if __name__ == '__main__':
    main()
