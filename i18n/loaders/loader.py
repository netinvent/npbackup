from .. import config
import io
import os.path


class I18nFileLoadError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return str(self.value)


class Loader(object):
    """Base class to load resources"""

    loaded_files = {}

    def __init__(self):
        super(Loader, self).__init__()

    def load_file(self, filename):
        try:
            with io.open(filename, 'r', encoding=config.get('encoding')) as f:
                return f.read()
        except IOError as e:
            raise I18nFileLoadError("error loading file {0}: {1}".format(filename, e.strerror)) from e

    def parse_file(self, file_content):
        raise NotImplementedError("the method parse_file has not been implemented for class {0}".format(self.__class__.__name__))

    def check_data(self, data, root_data):
        return True if root_data is None else root_data in data

    def get_data(self, data, root_data):
        # use .pop to remove used data from cache
        return data if root_data is None else data.pop(root_data)

    def load_resource(self, filename, root_data, remember_content):
        filename = os.path.abspath(filename)
        if filename in self.loaded_files:
            data = self.loaded_files[filename]
            if not data:
                # cache is missing or exhausted
                return {}
        else:
            file_content = self.load_file(filename)
            data = self.parse_file(file_content)
        if not self.check_data(data, root_data):
            raise I18nFileLoadError("error getting data from {0}: {1} not defined".format(filename, root_data))
        enable_memoization = config.get('enable_memoization')
        if enable_memoization:
            if remember_content:
                self.loaded_files[filename] = data
            else:
                self.loaded_files[filename] = None
        return self.get_data(data, root_data)
