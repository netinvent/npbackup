from collections import defaultdict


global_functions = {}
locales_functions = defaultdict(dict)


def add_function(name, func, locale=None):
    if locale:
        locales_functions[locale][name] = func
    else:
        global_functions[name] = func

def get_function(name, locale=None):
    if locale and name in locales_functions[locale]:
        return locales_functions[locale][name]
    return global_functions.get(name)
