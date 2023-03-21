import yaml

from . import Loader, I18nFileLoadError


class YamlLoader(Loader):
    """class to load yaml files"""

    loader = yaml.BaseLoader

    def __init__(self):
        super(YamlLoader, self).__init__()

    def parse_file(self, file_content):
        try:
            return yaml.load(file_content, Loader=self.loader)
        except yaml.YAMLError as e:
            raise I18nFileLoadError("invalid YAML: {0}".format(str(e))) from e
