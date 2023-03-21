try:
    __import__("yaml")
    yaml_available = True
except ImportError:
    yaml_available = False

try:
    __import__("json")
    json_available = True
except ImportError:
    json_available = False

# try to get existing path object
# in case if config is being reloaded
try:
    from . import load_path
    load_path.clear()
except ImportError:
    load_path = []

settings = {
    'filename_format': '{namespace}.{locale}.{format}',
    'file_format': 'yml' if yaml_available else 'json' if json_available else 'py',
    'available_locales': ['en'],
    'load_path': load_path,
    'locale': 'en',
    'fallback': 'en',
    'placeholder_delimiter': '%',
    'on_missing_translation': None,
    'on_missing_placeholder': None,
    'on_missing_plural': None,
    'encoding': 'utf-8',
    'namespace_delimiter': '.',
    'plural_few': 5,
    'skip_locale_root_data': False,
    'enable_memoization': False,
    'argument_delimiter': '|'
}

def set(key, value):
    if key not in settings:
        raise KeyError("Invalid setting: {0}".format(key))
    if key == 'placeholder_delimiter':
        # hacky trick to reload formatter's configuration
        from .translator import TranslationFormatter

        TranslationFormatter.delimiter = value
        del TranslationFormatter.pattern
        TranslationFormatter.__init_subclass__()
    elif key == 'load_path':
        load_path.clear()
        load_path.extend(value)
        return
    settings[key] = value

def get(key):
    return settings[key]
