## Report a Bug
Whenever encountering a bug follow these steps:

- Check if the bug is already reported on [github](https://github.com/hlorus/geometry_sketcher/labels/bug)
- Try to reliably reproduce the bug and simplify the steps to reproduce
- Collect the [logs](#access-logs)
- Post the bug on [github](https://github.com/hlorus/geometry_sketcher/issues/new?assignees=&labels=bug&template=bug-report.md&title=%5BBUG%5D)

## Console Output
Blender doesn't print system output in it's info editor but only in the
system terminal. Follow the guide below to access blender's system console.

=== "Linux / Mac"
    To see the system output blender has to be started from the terminal

    - Open a console by pressing Ctrl+Alt+T
    - Enter "blender" or the path to a specific blender version

=== "Windows"
    - In blender click Window->Toggle System Console

## Access Logs
The addon logs information to the [system console](#console-output) and to the system's temporary
folder. The filepath to this folder will be printed to the console whenever the
addon gets registered.


> geometry_sketcher:{INFO}: Logging into: C:\Users\USERNAME\AppData\Local\Temp\geometry_sketcher.log


## Documentation
Documentation is generated from the source repository with [MkDocs](https://www.mkdocs.org/).
In order to contribute either post a pull request with your changes on
[github](https://github.com/hlorus/geometry_sketcher) or ask on , [discord](https://discord.gg/GzpJsShgxa) for commit access.

> TODO: Workboard

## Development
If you'd like to help with development simply submit pull requests or reach out to me
[discord](https://discord.gg/GzpJsShgxa), twitter or email.

> TODO: Technical documentation

> TODO: Workboard
