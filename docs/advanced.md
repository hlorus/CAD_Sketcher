## Report a Bug
Whenever encountering a bug follow these steps:

- Check if the bug is already reported on [github](https://github.com/hlorus/CAD_Sketcher/labels/bug)
- Try to reliably reproduce the bug and simplify the steps to reproduce
- Collect the [addon logs](#access-logs)
- In case of a crash also collect blender's [crash report](https://docs.blender.org/manual/en/latest/troubleshooting/crash.html#:~:text=%2Do%20%25MEM%20.-,Crash%20Log,as%20some%20other%20debug%20information)
- Post the bug on [github](https://github.com/hlorus/CAD_Sketcher/issues/new?assignees=&labels=bug&template=bug-report.md&title=%5BBUG%5D)

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
Logs are helpful for debugging. Note that there are logs from the addon as well as from blender itself.

### Addon Logs
The addon logs information to the [system console](#console-output) and to the system's temporary
folder. The filepath to this folder will be printed to the console whenever the
addon gets registered.

> CAD_Sketcher:{INFO}: Logging into: C:\Users\USERNAME\AppData\Local\Temp\CAD_Sketcher.log

### Blender Crash Log
When blender crashes it writes a crash report file, see: [crash report](https://docs.blender.org/manual/en/latest/troubleshooting/crash.html#crash-log).


## Contribute
Help is always welcome. There are multiple ways to support the project.

### Testing
Just grab the latest version, play around, provide feedback and redo!

### Documentation
Documentation is generated from the source repository with [MkDocs](https://www.mkdocs.org/).
In order to contribute either post a pull request with your changes on
[github](https://github.com/hlorus/CAD_Sketcher) or ask on [discord](https://discord.gg/GzpJsShgxa) for commit access.

<!-- TODO: Workboard -->

### Development
If you'd like to help with development simply submit pull requests or reach out on
[discord](https://discord.gg/GzpJsShgxa), or [github](https://github.com/hlorus/CAD_Sketcher).

Take a look at the existing [code documentation](code_docs.md), this isn't complete yet,
if you are missing some specific information feel free to ask in the discord's contribute channel.

Have a look at the open issues on [github](https://github.com/hlorus/CAD_Sketcher/issues).
Some of them are alos marked with the "good first issue" tag, see [here](https://github.com/hlorus/CAD_Sketcher/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22). Also take a look at
the [raodmap](https://github.com/users/hlorus/projects/1) to see where the priority
currently lies.

<!-- ### Donate -->
