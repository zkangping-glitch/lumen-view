import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication
from lumenview import decoders, editing, theme
from lumenview.editing import EditState

@pytest.fixture(scope='session')
def app():
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app

@pytest.fixture
def photo(tmp_path):
    p = tmp_path / 'original.png'
    Image.new('RGBA', (80, 40), (150, 50, 20, 128)).save(p)
    return decoders.load_image(str(p))

@pytest.fixture
def animation(tmp_path):
    p = tmp_path / 'source.gif'
    frames = []
    for color in ((200, 0, 0, 255), (0, 200, 0, 255), (0, 0, 200, 255)):
        image = Image.new('RGBA', (80, 40), color)
        image.paste((0, 0, 0, 0), (0, 0, 8, 8))
        frames.append(image)
    frames[0].save(p, save_all=True, append_images=frames[1:], duration=[100, 200, 300], loop=2, disposal=2)
    return decoders.load_image(str(p))

def test_static_alpha_crop_original(photo, tmp_path):
    before = Path(photo.path).read_bytes()
    dest = tmp_path / 'edited.png'
    editing.export_image(photo, EditState(rotation=90, ratio='square', brightness=20), str(dest), 'PNG')
    with Image.open(dest) as im:
        assert im.size == (40, 40)
        assert im.getpixel((20, 20)) == (180, 60, 24, 128)
    assert Path(photo.path).read_bytes() == before

def test_jpeg_flattens_transparency(photo, tmp_path):
    dest = tmp_path / 'edited.jpg'
    editing.export_image(photo, EditState(), str(dest), 'JPEG', background='white')
    with Image.open(dest) as im:
        assert im.mode == 'RGB'
        assert im.getpixel((30, 20))[0] > 190

@pytest.mark.parametrize('fmt,suffix', [('GIF', 'gif'), ('动画 WebP', 'webp')])
def test_animation_frames_loop_alpha_timing(animation, tmp_path, fmt, suffix):
    dest = tmp_path / ('edited.' + suffix)
    editing.export_image(animation, EditState(ratio='square', rotation=90, speed=2), str(dest), fmt)
    loaded = decoders.load_image(str(dest))
    assert len(loaded.frames) == 3
    assert loaded.loop == 2
    assert loaded.width == loaded.height == 40
    assert [f.duration for f in loaded.frames] == [50, 100, 150]
    assert loaded.frames[0].image.pixelColor(20, 20).red() > 180
    editing.export_image(animation, EditState(), str(dest), fmt)
    loaded = decoders.load_image(str(dest))
    assert loaded.first.pixelColor(0, 0).alpha() == 0

def test_trim_and_static_frame(animation, tmp_path):
    state = EditState(start_ms=150, end_ms=400)
    assert editing.selected_frames(animation, state) == [(1, 150), (2, 100)]
    dest = tmp_path / 'frame.png'
    editing.export_image(animation, state, str(dest), 'PNG', frame_index=2)
    with Image.open(dest) as im:
        assert im.getpixel((30, 20))[2] > 180

def test_reject_original_and_hardlink(photo, tmp_path):
    with pytest.raises(ValueError, match='覆盖原图'):
        editing.export_image(photo, EditState(), photo.path, 'PNG')
    link = tmp_path / 'hardlink.png'
    os.link(photo.path, link)
    with pytest.raises(ValueError, match='覆盖原图'):
        editing.export_image(photo, EditState(), str(link), 'PNG')

def test_failed_save_is_atomic(photo, tmp_path, monkeypatch):
    dest = tmp_path / 'existing.png'
    dest.write_bytes(b'existing')
    def fail(*args, **kwargs): raise OSError('disk full')
    monkeypatch.setattr(Image.Image, 'save', fail)
    with pytest.raises(OSError):
        editing.export_image(photo, EditState(), str(dest), 'PNG')
    assert dest.read_bytes() == b'existing'
    assert not list(tmp_path.glob('.lumen-*'))

def test_budget_cannot_fall_back_to_qt(animation, monkeypatch):
    monkeypatch.setattr(decoders, 'MAX_ANIMATION_BYTES', 1)
    monkeypatch.setattr(decoders, '_load_qt', lambda _: pytest.fail('budget bypass'))
    with pytest.raises(decoders.ResourceLimitError):
        decoders.load_image(animation.path)

def test_svg_is_bounded(tmp_path, app):
    p = tmp_path / 'huge.svg'
    p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100000" height="100000"><rect width="100000" height="100000" fill="red"/></svg>')
    loaded = decoders.load_image(str(p))
    assert loaded.width == loaded.height == 2048

def test_history():
    h = editing.History()
    h.set(rotation=90); h.set(brightness=10); h.undo()
    assert h.state == EditState(rotation=90)
    h.redo(); assert h.state.brightness == 10
    h.undo(); h.set(flipped=True)
    assert not h.redo_stack

@pytest.mark.parametrize('fmt,suffix', [('GIF', 'gif'), ('动画 WebP', 'webp')])
def test_reordered_frames_with_individual_edits(animation, tmp_path, fmt, suffix):
    from lumenview.decoders import Frame, Loaded
    frames = [animation.frames[2], animation.frames[0], animation.frames[1]]
    extra = decoders._pil_to_qimage(Image.new('RGBA', (24, 24), 'magenta'))
    frames.insert(2, Frame(extra, 120))
    project = Loaded(animation.path, frames, animation.fmt, animation.width, animation.height,
                     loop=animation.loop)
    states = [EditState() for _ in frames]
    states[1] = EditState(rotation=180)
    dest = tmp_path / ('reordered.' + suffix)
    editing.export_image(project, EditState(), str(dest), fmt, frame_states=states)
    reopened = decoders.load_image(str(dest))
    assert len(reopened.frames) == 4
    assert reopened.loop == animation.loop
    assert [f.duration for f in reopened.frames] == [300, 100, 120, 200]
