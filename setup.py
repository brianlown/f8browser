# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['f8browser']

package_data = \
{'': ['*'], 'f8browser': ['lib/*']}

install_requires = \
['click>=7.1.1,<8.0.0',
 'dtegui @ git+https://github.com/brianlown/dtegui.git@master',
 'ipaddress>=1.0.23,<2.0.0',
 'paramiko>=2.7.1,<3.0.0',
 'pygubu>=0.9.8,<0.10.0',
 'pynput>=1.6.8,<2.0.0',
 'sshexpect @ git+https://github.com/brianlown/sshexpect.git@master']

setup_kwargs = {
    'name': 'f8browser',
    'version': '0.1.0',
    'description': 'Browsing utility for F8 shelves and modules',
    'long_description': None,
    'author': 'brianlown',
    'author_email': '62453448+brianlown@users.noreply.github.com',
    'maintainer': None,
    'maintainer_email': None,
    'url': None,
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.4,<4.0',
}


setup(**setup_kwargs)
