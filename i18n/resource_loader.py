import os.path

from . import config
from .loaders import Loader, I18nFileLoadError
from . import translations

loaders = {}

PLURALS = {"zero", "one", "few", "many"}


def register_loader(loader_class, supported_extensions):
    if not issubclass(loader_class, Loader):
        raise ValueError("loader class should be subclass of i18n.Loader")

    loader = loader_class()
    for extension in supported_extensions:
        loaders[extension] = loader


def load_resource(filename, root_data, remember_content=False):
    extension = os.path.splitext(filename)[1][1:]
    if extension not in loaders:
        raise I18nFileLoadError("no loader available for extension {0}".format(extension))
    return loaders[extension].load_resource(filename, root_data, remember_content)


def init_loaders():
    init_python_loader()
    if config.yaml_available:
        init_yaml_loader()
    if config.json_available:
        init_json_loader()


def init_python_loader():
    from .loaders import PythonLoader
    register_loader(PythonLoader, ["py"])


def init_yaml_loader():
    from .loaders import YamlLoader
    register_loader(YamlLoader, ["yml", "yaml"])


def init_json_loader():
    from .loaders import JsonLoader
    register_loader(JsonLoader, ["json"])


def load_config(filename):
    settings_data = load_resource(filename, "settings")
    for key, value in settings_data.items():
        config.set(key, value)


def get_namespace_from_filepath(filename):
    namespace = os.path.dirname(filename).strip(os.sep).replace(os.sep, config.get('namespace_delimiter'))
    format = config.get('filename_format')
    if '{namespace}' in format:
        try:
            splitted_filename = os.path.basename(filename).split('.')
            if namespace:
                namespace += config.get('namespace_delimiter')
            namespace += splitted_filename[format.split(".").index('{namespace}')]
        except ValueError as e:
            raise I18nFileLoadError("incorrect file format.") from e
    return namespace


def load_translation_file(filename, base_directory, locale=None):
    if locale is None:
        locale = config.get('locale')
    skip_locale_root_data = config.get('skip_locale_root_data')
    root_data = None if skip_locale_root_data else locale
    # if the file isn't dedicated to one locale and may contain other `root_data`s
    remember_content = "{locale}" not in config.get("filename_format") and root_data
    translations_dic = load_resource(os.path.join(base_directory, filename), root_data, remember_content)
    namespace = get_namespace_from_filepath(filename)
    load_translation_dic(translations_dic, namespace, locale)


def reload_everything():
    translations.clear()
    Loader.loaded_files.clear()


def load_translation_dic(dic, namespace, locale):
    if namespace:
        namespace += config.get('namespace_delimiter')
    for key, value in dic.items():
        if type(value) == dict and len(PLURALS.intersection(value)) < 2:
            load_translation_dic(value, namespace + key, locale)
        else:
            translations.add(namespace + key, value, locale)


def load_directory(directory, locale):
    for f in os.listdir(directory):
        path = os.path.join(directory, f)
        if os.path.isfile(path) and path.endswith(config.get('file_format')):
            if '{locale}' in config.get('filename_format') and not locale in f:
                continue
            load_translation_file(f, directory, locale)


def search_translation(key, locale=None):
    if locale is None:
        locale = config.get('locale')
    splitted_key = key.split(config.get('namespace_delimiter'))
    namespace = splitted_key[:-1]
    if not namespace and '{namespace}' not in config.get('filename_format'):
        for directory in config.get('load_path'):
            load_directory(directory, locale)
    else:
        for directory in config.get('load_path'):
            recursive_search_dir(namespace, '', directory, locale)


def recursive_search_dir(splitted_namespace, directory, root_dir, locale):
    namespace = splitted_namespace[0] if splitted_namespace else ""
    seeked_file = config.get('filename_format').format(namespace=namespace, format=config.get('file_format'), locale=locale)
    dir_content = os.listdir(os.path.join(root_dir, directory))
    if seeked_file in dir_content:
        load_translation_file(os.path.join(directory, seeked_file), root_dir, locale)
    elif namespace in dir_content:
        recursive_search_dir(splitted_namespace[1:], os.path.join(directory, namespace), root_dir, locale)
