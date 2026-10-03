import sys
import json
from pathlib import Path
from backup_proof import audit, validate_roots
from desktop_ui import App, resource_root
from friendly import UserInputError
TITLE = 'Backup Proof'
KIND = 'backup'


def check(values):
    if not values['first'] or not values['second']: raise UserInputError('Choose both the original folder and the backup folder.')
    return audit(values['first'], values['second'])
def demo(): return audit(resource_root() / 'examples/source', resource_root() / 'examples/backup')
def make_app(window): return App(window, KIND, TITLE, demo, check, validate_output=validate_roots)
def extra_smoke():
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        source, backup = Path(directory) / 'original', Path(directory) / 'copy'
        source.mkdir(); backup.mkdir()
        (source / 'note.txt').write_bytes(b'good')
        (backup / 'note.txt').write_bytes(b'good')
        assert audit(source, backup)['status'] == 'verified', 'Matching copy was not verified'
        (backup / 'note.txt').write_bytes(b'bad!')
        result = audit(source, backup)
        assert result['status'] == 'attention', 'Changed copy was not detected'
        assert any(item['status'] == 'mismatch' for item in result['findings'])


def self_test(result_path=None):
    import tempfile
    import time
    import tkinter as tk
    import desktop_ui
    try:
        with tempfile.TemporaryDirectory() as directory:
            desktop_ui.data_root = lambda: Path(directory)
            window = tk.Tk(); window.withdraw()
            app = make_app(window)
            app.start_demo()
            deadline = time.monotonic() + 20
            while app.busy and time.monotonic() < deadline:
                window.update(); time.sleep(0.02)
            assert not app.busy and app.report and app.report.exists(), 'Example did not finish'
            assert app.result.get('demo') is True
            assert str(app.run_button.cget('state')) == 'normal'
            window.destroy()
            extra_smoke()
        result = {'ok': True, 'tool': TITLE, 'checks': ['desktop window', 'example', 'report', 'controls restored', 'engine smoke']}
        code = 0
    except Exception as error:
        result = {'ok': False, 'tool': TITLE, 'error': str(error)}
        code = 1
    if result_path: Path(result_path).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return code


def main():
    import tkinter as tk
    if '--self-test' in sys.argv:
        index = sys.argv.index('--self-test')
        return self_test(sys.argv[index+1] if len(sys.argv) > index+1 else None)
    window = tk.Tk()
    app = make_app(window)
    if '--preview' in sys.argv: window.after(200, app.start_demo)
    window.mainloop()
    return 0


if __name__ == '__main__':
    if KIND == 'service' and len(sys.argv) == 5 and sys.argv[1] == '--resolve-worker':
        sys.exit(resolver_worker_file(*sys.argv[2:]))
    sys.exit(main())
