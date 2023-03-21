from string import Template

from . import config
from . import resource_loader
from . import translations
from .custom_functions import get_function


class TranslationFormatter(Template, dict):
    delimiter = config.get('placeholder_delimiter')
    idpattern = r"""
        \w+                      # name
        (
            \(
                [^\(\){}]*       # arguments
            \)
        )?
    """

    def __init__(self, translation_key, template):
        super(TranslationFormatter, self).__init__(template)
        self.translation_key = translation_key

    def format(self, locale, **kwargs):
        self.clear()
        self.update(kwargs)
        self.locale = locale
        if config.get('on_missing_placeholder'):
            return self.substitute(self)
        else:
            return self.safe_substitute(self)

    def __getitem__(self, key: str):
        try:
            name, _, args = key.partition("(")
            if args:
                f = get_function(name, self.locale)
                if f:
                    i = f(**self)
                    args = args.strip(')').split(config.get('argument_delimiter'))
                    try:
                        return args[i]
                    except (IndexError, TypeError) as e:
                        raise ValueError(
                            "No argument {0!r} for function {1!r} (in {2!r})"
                            .format(i, name, self.template)
                        ) from e
                raise KeyError(
                    "No function {0!r} found for locale {1!r} (in {2!r})"
                    .format(name, self.locale, self.template)
                )
            return super().__getitem__(key)
        except KeyError:
            on_missing = config.get('on_missing_placeholder')
            if not on_missing or on_missing == "error":
                raise
            return on_missing(self.translation_key, self.locale, self.template, key)


def t(key, **kwargs):
    locale = kwargs.pop('locale', config.get('locale'))
    if translations.has(key, locale):
        return translate(key, locale=locale, **kwargs)
    else:
        resource_loader.search_translation(key, locale)
        if translations.has(key, locale):
            return translate(key, locale=locale, **kwargs)
        elif locale != config.get('fallback'):
            return t(key, locale=config.get('fallback'), **kwargs)
    if 'default' in kwargs:
        return kwargs['default']
    on_missing = config.get('on_missing_translation')
    if on_missing == "error":
        raise KeyError('key {0} not found'.format(key))
    elif on_missing:
        return on_missing(key, locale, **kwargs)
    else:
        return key


def translate(key, **kwargs):
    locale = kwargs.pop('locale', config.get('locale'))
    translation = translations.get(key, locale=locale)
    if 'count' in kwargs:
        translation = pluralize(key, locale, translation, kwargs['count'])
    return TranslationFormatter(key, translation).format(locale, **kwargs)


def pluralize(key, locale, translation, count):
    return_value = key
    try:
        if type(translation) != dict:
            return_value = translation
            raise KeyError('use of count witouth dict for key {0}'.format(key))
        if count == 0:
            if 'zero' in translation:
                return translation['zero']
        elif count == 1:
            if 'one' in translation:
                return translation['one']
        elif count <= config.get('plural_few'):
            if 'few' in translation:
                return translation['few']
        if 'many' in translation:
            return translation['many']
        else:
            raise KeyError('"many" not defined for key {0}'.format(key))
    except KeyError:
        on_missing = config.get('on_missing_plural')
        if on_missing == "error":
            raise
        elif on_missing:
            return on_missing(key, locale, translation, count)
        else:
            return return_value
