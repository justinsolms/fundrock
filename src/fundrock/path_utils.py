"""The ``path_utils`` module for managing project paths. """

import os
from pathlib import Path

# Data path environment variable name
_DATA = "DATA_PATH"

# Config path
_CONFIG = "config"

# Tests path
_TESTS = "tests"

# Variable data path
_VAR = "var"
# Variable data path for tests - should always delete after tests!
_VAR_TEST = "var_test"

# Log, tmp an cache path under variable data path
_LOG = "log"
_TMP = "tmp"
_CACHE = "cache"
_DATABASE = "db"


# Authentication certificates path
_CERTIFICATES = 'certificates'

# Resources path to such as art, logos, html, css, .md, .rst, .txt, content, etc.
_RESOURCES = 'resources'
# Templates under _RESOURCES for html, css, etc.
_TEMPLATES = 'templates'
# Content under _RESOURCES for .md, .rst, .txt, etc.
_CONTENT = 'content'
# Art under _RESOURCES for images, logos, etc.
_ART = 'art'

# General output path
_OUTPUT = '~/Documents/MyDrive/allocate'

def get_project_path() -> str:
    """Return the absolute path of the project root (parent of ``src``)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

def get_output_path(sub_path: str | None = None) -> str:
    output_path = os.path.expanduser(_OUTPUT)
    # Join the sub_path if it is not None.
    if sub_path is not None:
        # Check that `sub_path`` does not contain a filename, i.e., no `.`
        if Path(sub_path).suffix != '':
            raise ValueError("The `sub_path` parameter should not contain a filename.")
        output_path = os.path.join(output_path, sub_path)
    # Create the output directory with parents if it does not exist
    os.makedirs(output_path, exist_ok=True)
    # Get the output path string
    return output_path

def get_certificates_path(sub_path: str | None = None) -> str:
    project_path = get_project_path()
    certificates_path = os.path.join(project_path, _CERTIFICATES)
    if not os.path.exists(certificates_path):
        raise FileNotFoundError("Certificates directory not found")
    # Add the sub_path if it is not None
    if sub_path is not None:
        certificates_path = os.path.join(certificates_path, sub_path)
    return certificates_path

def get_resources_path(sub_path: str | None = None) -> str:
    project_path = get_project_path()
    resources_path = os.path.join(project_path, _RESOURCES)
    if not os.path.exists(resources_path):
        raise FileNotFoundError("Resources directory not found")
    # Add the sub_path if it is not None
    if sub_path is not None:
        resources_path = os.path.join(resources_path, sub_path)
    return resources_path

def get_templates_path(sub_path: str | None = None) -> str:
    resources_dir = get_resources_path()
    templates_path = os.path.join(resources_dir, _TEMPLATES)
    if not os.path.exists(templates_path):
        raise FileNotFoundError("Templates directory not found")
    # Add the sub_path if it is not None
    if sub_path is not None:
        templates_path = os.path.join(templates_path, sub_path)
    return templates_path

def get_content_path(sub_path: str | None = None) -> str:
    resources_dir = get_resources_path()
    content_path = os.path.join(resources_dir, _CONTENT)
    if not os.path.exists(content_path):
        raise FileNotFoundError("Content directory not found")
    # Add the sub_path if it is not None
    if sub_path is not None:
        content_path = os.path.join(content_path, sub_path)
    return content_path

def get_art_path(sub_path: str | None = None) -> str:
    resources_dir = get_resources_path()
    art_path = os.path.join(resources_dir, _ART)
    if not os.path.exists(art_path):
        raise FileNotFoundError("Art directory not found")
    # Add the sub_path if it is not None
    if sub_path is not None:
        art_path = os.path.join(art_path, sub_path)
    return art_path

def get_data_path(sub_path: str | None = None) -> str:
    data_path = os.environ.get(_DATA)
    if data_path is None:
        raise ValueError(f"Environment variable {_DATA} not set.")
    # Add the sub_path if it is not None
    if sub_path is not None:
        data_path = os.path.join(data_path, sub_path)
    return os.path.abspath(data_path)

def get_config_path(sub_path: str | None = None) -> str:
    project_path = get_project_path()
    # Construct the full path to the config folder
    config_path = os.path.join(project_path, _CONFIG)
    # Add the sub_path if it is not None
    if sub_path is not None:
        config_path = os.path.join(config_path, sub_path)
    return os.path.abspath(config_path)

def get_tests_path(sub_path: str | None = None) -> str:
    project_path = get_project_path()
    # Construct the full path to the config folder
    tests_path = os.path.join(project_path, _TESTS)
    # Add the sub_path if it is not None
    if sub_path is not None:
        tests_path = os.path.join(tests_path, sub_path)
    return os.path.abspath(tests_path)

def get_var_path(sub_path: str | None = None, testing: bool = False) -> str:
    project_path = get_project_path()
    # Construct the full path to the config folder
    if testing:
        var_path = os.path.join(project_path, _VAR_TEST)
    else:
        var_path = os.path.join(project_path, _VAR)
    # Create the var directory if it does not exist
    if not os.path.exists(var_path):
        os.makedirs(var_path)
    # Add the sub_path if it is not None
    if sub_path is not None:
        var_path = os.path.join(var_path, sub_path)
    return os.path.abspath(var_path)

def get_log_path(sub_path: str | None = None, testing: bool = False) -> str:
    var_dir = get_var_path(testing=testing)
    log_path = os.path.join(var_dir, _LOG)
    # Create the log directory if it does not exist
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    # Add the sub_path if it is not None
    if sub_path is not None:
        log_path = os.path.join(log_path, sub_path)
    return os.path.abspath(log_path)

def get_tmp_path(sub_path: str | None = None, testing: bool = False) -> str:
    var_dir = get_var_path(testing=testing)
    tmp_path = os.path.join(var_dir, _TMP)
    # Create the tmp directory if it does not exist
    if not os.path.exists(tmp_path):
        os.makedirs(tmp_path)
    # Add the sub_path if it is not None
    if sub_path is not None:
        tmp_path = os.path.join(tmp_path, sub_path)
    return os.path.abspath(tmp_path)

def get_cache_path(sub_path: str | None = None, testing: bool = False) -> str:
    var_dir = get_var_path(testing=testing)
    cache_path = os.path.join(var_dir, _CACHE)
    # Create the cache directory if it does not exist
    if not os.path.exists(cache_path):
        os.makedirs(cache_path)
    # Add the sub_path if it is not None
    if sub_path is not None:
        cache_path = os.path.join(cache_path, sub_path)
    return os.path.abspath(cache_path)

def get_database_path(sub_path: str | None = None, testing: bool = False) -> str:
    var_dir = get_var_path(testing=testing)
    database_path = os.path.join(var_dir, _DATABASE)
    # Create the database directory if it does not exist
    if not os.path.exists(database_path):
        os.makedirs(database_path)
    # Add the sub_path if it is not None
    if sub_path is not None:
        database_path = os.path.join(database_path, sub_path)
    return os.path.abspath(database_path)

