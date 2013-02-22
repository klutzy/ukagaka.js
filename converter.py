from wand.image import Image


def normalize_overlay_id(overlay_id):
    if not overlay_id.endswith('png'):
        overlay_id = 'surface%s.png' % overlay_id
    return overlay_id


class SurfaceManager(object):
    def __init__(self, surfaces, path):
        self.surfaces = surfaces
        self.path = path

        # (surface_id, overlay_id, ...) -> Image
        # for vanilla image, use (surface_id,)
        # all ids are png filename
        self.image_map = {}

        # overlay_id -> (x,y)
        # assumes only one position per one image
        self.position_map = {}

        # surface[n].animation{i}.pattern{j}.overlay
        # n, i, j all int
        # animation_map[(n,i,j)] -> image_map_id
        self.animation_map = {}
        # overlay_map[n] -> image_map_id
        self.overlay_map = {}

        self._init_position_map()

    def _init_position_map(self):
        for surface in self.surfaces:
            for overlay_info in surface.elements:
                _, overlay_id, x, y = overlay_info
                self.position_map[overlay_id] = (x, y)
            for animation_list in surface.animations.values():
                for anim in animation_list:
                    if not anim[0].startswith('pattern'):
                        continue
                    if anim[1] != 'overlay':
                        continue

                    overlay_id = anim[2]
                    if overlay_id:
                        x, y = anim[-2:]
                        self.position_map[overlay_id] = (x, y)

    def load_image(self, name):
        # low-level api for get_image
        image = Image(filename=self.path + '/' + name)
        return image

    def get_image(self, id_list):
        id_list = tuple(id_list)

        if id_list in self.image_map:
            return self.image_map[id_list]

        image = None
        if len(id_list) == 1:
            image = self.load_image(id_list[0])
        else:
            image = self.get_image(id_list[:-1])[:]
            overlay = self.load_image(id_list[-1])
            x, y = self.position_map[id_list[-1]]
            image.composite(overlay, x, y)

        self.image_map[id_list] = image
        return image

    def convert_overlays(self):
        for surf in self.surfaces:
            self.convert_surface_overlay(surf)
            self.convert_surface_animations(surf)

    def convert_surface_overlay(self, surface):
        id_list = None
        if surface.elements:
            id_list = [i[1] for i in surface.elements]
        else:
            overlay_id = surface.overlay_id
            id_list = (overlay_id,)

        self.overlay_map[surface.index] = id_list
        return self.get_image(id_list)

    def convert_surface_animations(self, surface):
        for animation_id in surface.animations:
            animation = surface.animations[animation_id]
            for movement in animation:
                if not movement[0].startswith('pattern'):
                    continue
                if movement[1] != 'overlay':
                    # TODO
                    continue
                overlay_id = movement[2]
                if overlay_id is None:
                    # TODO default overlay
                    continue
                if not overlay_id.endswith(".png"):
                    overlay_id = "surface%s.png" % overlay_id

                id_list = (surface.overlay_id, overlay_id)
                self.get_image(id_list)

                movement_id = int(movement[0][7:])
                frame_id = (surface.index, animation_id, movement_id)
                self.animation_map[frame_id] = id_list

    def generate_images(self, path):
        image_id_map = {}
        for i, image_id in enumerate(self.image_map):
            image_id_map[image_id] = i
            image = self.image_map[image_id]
            filename = path + '/image-%.4d.png' % i
            image.save(filename=filename)


class Surface(object):
    def __init__(self, index, overlay_id):
        self.index = index
        self.overlay_id = overlay_id
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


def parse_surface(index, blob):
    overlay_id = normalize_overlay_id("%.4d" % index)
    surface = Surface(index, overlay_id)
    for cmd in blob:
        cmd = cmd.split(',')
        c = cmd[0]
        if c.startswith('collision'):
            surface.collisions.append(cmd)
        elif c.startswith('animation'):
            a = c.split('.')
            animation_id = int(a[0][9:])
            args = [a[1]] + cmd[1:]
            # two possibilities:
            #   internal, interval_info
            #   pattern{j}, overlay, overlay_id, duration?, x, y
            if args[0].startswith('pattern') and args[1] == 'overlay':
                if args[2] == '-1':
                    overlay_id = None
                    args = args[:2] + [overlay_id]
                else:
                    overlay_id = normalize_overlay_id(args[2])
                    x = int(args[4])
                    y = int(args[5])
                    args = args[:2] + [overlay_id, args[3], x, y]

            if animation_id not in surface.animations:
                surface.animations[animation_id] = []
            surface.animations[animation_id].append(args)

        elif c.startswith('element'):
            element_i = int(c[7:])
            if cmd[1] != 'overlay':
                # TODO
                continue
            _, _, overlay_id, x, y = cmd
            overlay_id = normalize_overlay_id(overlay_id)
            x = int(x)
            y = int(y)
            args = (element_i, overlay_id, x, y)
            surface.elements.append(args)

    return surface


def parse(text, path):
    if not text:
        raise ValueError("no text")
    ret = []
    for title, blob in parse_blob(text):
        if title == 'descript':
            continue
        if title.startswith('surface'):
            index = int(title[7:])
            surface = parse_surface(index, blob)
            ret.append(surface)

    return SurfaceManager(ret, path)


def main():
    import sys
    path = './master'
    if len(sys.argv) > 1:
        path = sys.argv[1]
    fn = path + '/surfaces.txt'
    p = parse(open(fn).read(), path)

    p.convert_overlays()
    print p.overlay_map
    print
    print p.animation_map

    p.generate_images('./out')

    return p

if __name__ == '__main__':
    main()
