import wand.image
import json


DURATION_DEFAULT = 1000


def animation_weight(interval):
    weight_map = {
        'never': 0,
        'sometimes': 30,  # XXX arbitrary
        'always': 100,
        'runonce': 100,  # XXX should be treated separately
    }
    return weight_map[interval]


class Overlay(object):
    def __init__(self, resource_id, x=0, y=0):
        if not resource_id.endswith('png'):
            if len(resource_id) < 4:
                resource_id = '0' * (4 - len(resource_id)) + resource_id
            resource_id = 'surface%s.png' % resource_id
        self.resource_id = resource_id
        self.x = x
        self.y = y

    def __str__(self):
        return "<{}: {}, {}>".format(self.resource_id, self.x, self.y)

    def __eq__(self, other):
        return self.resource_id == other.resource_id and \
            self.x == other.x and self.y == other.y

    def __hash__(self):
        return hash((self.resource_id, self.x, self.y))


class Image(tuple):
    @staticmethod
    def extend(image, overlay):
        ret = list(image) + [overlay]
        return Image(ret)

    def __str__(self):
        return ", ".join("{}:{},{}".format(i.resource_id, i.x, i.y)
                         for i in self)


class Animation(object):
    def __init__(self, animation_id):
        self.animation_id = animation_id
        self.interval = None
        self.patterns = []

    def __str__(self):
        return "<{}: {} patterns, {}>".format(
            self.animation_id, len(self.patterns), self.interval)


class Surface(object):
    def __init__(self, index):
        self.index = index
        self.collisions = []  # not used

        self.animations = {}  # animation_id -> Animation()
        self.base_image = None


class Ukagaka(object):
    def __init__(self, image_path):
        self.surfaces = []
        self.image_path = image_path

        self.image_width = None
        self.image_height = None

        self.image_id_map = {}
        self.total_images = 0

    def register_image(self, image):
        if image in self.image_id_map:
            return self.image_id_map[image]

        image_id = self.total_images
        self.image_id_map[image] = image_id
        self.total_images += 1
        return image_id

    def parse(self, text):
        if not text:
            raise ValueError("no text")
        for title, blob in self._parse_blob(text):
            if title.startswith('surface'):
                index = int(title[7:])
                self._parse_surface(index, blob)

    def _parse_surface(self, index, blob):
        surface = Surface(index)
        self.surfaces.append(surface)

        base_overlays = []
        for line in blob:
            cmd = line.split(',')  # XXX "a,b,(c,d)"
            c = cmd[0]
            if c.startswith('collision'):
                surface.collisions.append(cmd)
            elif c.startswith('animation'):
                pass  # later
            elif c.startswith('element'):
                #element_index = int(c[7:])
                if cmd[1] != 'overlay':
                    # TODO
                    continue
                _, _, resource_id, x, y = cmd
                x = int(x)
                y = int(y)
                overlay = Overlay(resource_id, x, y)
                base_overlays.append(overlay)

        if base_overlays:
            surface.base_image = Image(base_overlays)
        else:
            # use default overlay image
            overlay = Overlay(str(index))
            surface.base_image = Image((overlay,))

        self.register_image(surface.base_image)
        #surface.frames[0].image = surface.base_image

        # now surface has base_image
        for line in blob:
            cmd = line.split(',')  # XXX "a,b,(c,d)"
            c = cmd[0]
            if c.startswith('animation'):
                a = c.split('.')  # animation_id.{interval,pattern_id,...}
                animation_id = a[0][9:]  # "1", "2", "3"
                if animation_id not in surface.animations:
                    surface.animations[animation_id] = Animation(animation_id)
                self._parse_animation_info(surface,
                                           surface.animations[animation_id],
                                           a[1], cmd[1:])
        return surface

    def _parse_animation_info(self, surface, animation, info_type, args):
        if info_type == 'interval':
            animation.interval = args[0]

        elif info_type.startswith('pattern'):
            pattern = None
            pattern_type = args[0]  # overlay, base, alternativestart, ...
            pattern_args = args[1:]
            if pattern_type in ['overlay', 'base']:
                resource_id = pattern_args[0]
                image = None
                duration = None
                if resource_id == '-1':
                    image = surface.base_image
                else:
                    duration = int(pattern_args[1])
                    x = int(pattern_args[2])
                    y = int(pattern_args[3])
                    overlay = Overlay(resource_id, x, y)
                    image = Image.extend(surface.base_image, overlay)
                    if pattern_type == 'base':
                        image = Image((overlay,))
                    self.register_image(image)
                pattern = ("frame", image, duration)

            elif pattern_type == 'alternativestart':
                # (list,of,animation,ids)
                # e.g. (0,1)
                # XXX parser splitted "(0,1)" into "(0", "1)"!
                branches = args[1:]
                branches[0] = branches[0].replace('(', '')
                branches[-1] = branches[-1].replace(')', '')
                pattern = ("alternativestart", branches)

            # XXX pattern_id ignored
            animation.patterns.append(pattern)

    def _parse_blob(self, text):
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

    def _load_img(self, image, image_map):
        if image in image_map:
            return image_map[image]

        filename = image[-1].resource_id
        img = wand.image.Image(filename=self.image_path + '/' + filename)

        if len(image) > 1:
            base = self._load_img(image[:-1], image_map)[:]
            base.composite(img, image[-1].x, image[-1].y)
            img = base

        image_map[image] = img
        return img

    def _image_to_clippy_pos(self, image):
        i = self.image_id_map[image]
        return [[i * self.image_width, 0]]

    def _surface_to_clippy_frames(self, surface):
        ret = []

        initial_frame = {}
        initial_frame['images'] = self._image_to_clippy_pos(surface.base_image)
        initial_frame['duration'] = DURATION_DEFAULT

        final_frame = initial_frame.copy()

        keyframes = {}
        branches = []  # (from, to, weight)

        ret.append(initial_frame)

        for animation_id in surface.animations:
            animation = surface.animations[animation_id]
            keyframe = len(ret)  # start frame of animation
            n_frames = 0
            for pattern in animation.patterns:
                pattern_type = pattern[0]
                pattern_args = pattern[1:]

                if pattern_type == 'alternativestart':
                    # not a frame. register possible branches here.
                    # note that we don't know other animations' frame id
                    # thus save branching info at surface.branches.
                    # NOTE multi-level alternative start is unsupported
                    current_frame = keyframe + n_frames - 1
                    if not n_frames:
                        current_frame = 0

                    len_alters = len(pattern[1:])
                    alternatives = pattern_args[0]
                    for i, anim_id in enumerate(alternatives):
                        weight = animation_weight(animation.interval)
                        weight = (i + 1) * weight / len_alters
                        branches.append((current_frame, anim_id, weight))

                elif pattern_type == 'frame':
                    image, duration = pattern_args

                    if duration is None:
                        duration = DURATION_DEFAULT

                    frame = {}
                    frame['images'] = self._image_to_clippy_pos(image)
                    frame['duration'] = duration
                    ret.append(frame)
                    n_frames += 1

            if n_frames > 0:
                keyframes[animation_id] = keyframe
                last_frame = keyframe + n_frames - 1
                branches.append((last_frame, -1, 100))

        ret.append(final_frame)

        branches.append((0, 0, 95))
        branches.append((0, -1, 100))

        for from_frame, to_id, weight in branches:
            if not 'branching' in ret[from_frame]:
                ret[from_frame]['branching'] = {'branches': []}
            frame_index = None
            if to_id == -1:
                frame_index = len(ret) - 1
            elif to_id == 0:
                frame_index = 0
            else:
                frame_index = keyframes[to_id]
            ret[from_frame]['branching']['branches'].append({
                'frameIndex': frame_index,
                'weight': weight,
            })

        return ret

    def to_clippy(self, path):
        self._make_clippy_img(path, self.image_id_map)

        animations = {}
        for surface in self.surfaces:
            frames = self._surface_to_clippy_frames(surface)
            animation_name = str(surface.index)
            animation_name = "Surface" + animation_name
            if surface.index == 0:
                animation_name = "IdleNormal"
            elif surface.index == 1:
                animation_name = "Show"
            animations[animation_name] = {'frames': frames}

        json_data = {
            'overlayCount': 1,
            'sounds': [],
            'framesize': [self.image_width, self.image_height],
            'animations': animations,
        }
        json_str = json.dumps(json_data, indent=4, separators=(',', ': '))
        ret = "clippy.ready('Ukagaka', %s);" % json_str
        open(path + '/agent.js', 'w').write(ret)

    def _make_clippy_img(self, path, image_id_map):
        image_id_list = [None for _ in image_id_map.keys()]
        for image in image_id_map:
            image_id_list[image_id_map[image]] = image
        image0 = image_id_list[0]

        image_map = {}  # image to actual image
        img = self._load_img(image0, image_map)
        self.image_width = img.width
        self.image_height = img.height

        # clippy.js requires all images has same size
        # TODO error if image sizes differ
        total_image_width = self.image_width * len(image_id_list)
        total_img = wand.image.Image(width=total_image_width,
                                     height=self.image_height)

        for i, image in enumerate(image_id_list):
            img = self._load_img(image, image_map)
            x = self.image_width * i
            total_img.composite(img, x, 0)
        filename = path + '/map.png'
        total_img.save(filename=filename)


def main():
    import sys
    path = './master'
    if len(sys.argv) > 1:
        path = sys.argv[1]
    fn = path + '/surfaces.txt'
    uka = Ukagaka(path)
    uka.parse(open(fn).read())

    uka.to_clippy('./out')

    return uka

if __name__ == '__main__':
    main()
