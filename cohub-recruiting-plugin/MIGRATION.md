# Migration Guide

## From Built-in Skill to Plugin

The recruiting assistant was originally embedded in the CoHub core codebase. It has been extracted into this independent plugin.

### What Changed

1. **CoHub Core**: Added a generic plugin hook system (`skill_hooks.py`). Removed all recruiting-specific logic from `tool_guard_mixin.py` and `model_factory.py`.

2. **Scripts**: `start_copaw_local.sh`, `setup_recruiting_assistant_local.sh`, and build scripts no longer call `recruiting_bootstrap`. The plugin is auto-discovered via entry-points.

3. **Plugin**: All recruiting code (skill, 3 MCPs, tool guard, config, models, renderer, match reasoner) now lives in this independent package.

### Migration Steps

1. Install the plugin:
   ```bash
   pip install cohub-recruiting-plugin
   ```

2. Run the installer to configure your workspace:
   ```python
   from cohub_recruiting.installer import install_recruiting_plugin
   install_recruiting_plugin()
   ```

3. Restart CoHub. The plugin's hooks are automatically registered.

### Compatibility

- Requires CoHub version with `skill_hooks.py` (the generic hook system)
- Python 3.10+
- All existing skill configurations and browser profiles are compatible
