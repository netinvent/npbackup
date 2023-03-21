from . import resource_loader
from .resource_loader import Loader, I18nFileLoadError, register_loader, load_config, reload_everything
from .translator import t
from .translations import add as add_translation
from .custom_functions import add_function
from . import config
from .config import set, get

resource_loader.init_loaders()

load_path = config.get('load_path')
