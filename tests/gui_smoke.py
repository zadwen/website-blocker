"""Nonprivileged UI smoke test. Never installs or edits machine settings."""
import copy
import os
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config, rules
from ui.app import App

with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'WB_DATA_DIR': folder}), \
        patch('ui.app.IS_WINDOWS', False), patch('ui.app.install.daemon_running', return_value=False):
    app = App()
    app.cfg = copy.deepcopy(config.DEFAULT_CONFIG)
    app.cfg['rules'] = [rules.make_rule('youtube.com', 'forever'),
                        rules.make_rule('example.com', 'schedule', start='22:00', end='07:00', days=[0, 1])]
    app.build()
    app.deiconify()
    app.update()
    assert len(app.tree.get_children()) == 2
    app.search_var.set('youtube')
    app.update()
    assert len(app.tree.get_children()) == 1
    app.check_var.set('https://video.youtube.com/path')
    app.check_domain()
    assert 'Browser domain rule: covered' in app.coverage_label.cget('text')
    app.search_var.set('')
    app.tree.selection_set(app.cfg['rules'][0]['id'])
    app.toggle_rule()
    assert app.cfg['rules'][0]['enabled'] is False
    app.toggle_rule()
    assert app.cfg['rules'][0]['enabled'] is True
    app.destroy()
print('GUI smoke test passed')
