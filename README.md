# viyapy
Utilities for SAS Viya

## Updating the package

https://packaging.python.org/en/latest/tutorials/packaging-projects/

update the version in the setup.cfg

py -m build

This command should output a lot of text and once completed should generate two files in the dist directory:

dist/
  example-package-YOUR-USERNAME-HERE-0.0.1-py3-none-any.whl
  example-package-YOUR-USERNAME-HERE-0.0.1.tar.gz
  
  
py -m twine upload dist/*

You will be prompted for a username and password. For the username, use __token__. For the password, use the token value, including the pypi- prefix.
