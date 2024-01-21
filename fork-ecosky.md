This fork includes the following improvements:

**Driver Usability Features to improve parametric design workflow**

While CAD Sketcher already had support for using Blender drivers to centralize the data used to specify values on constraints, it can be
cumbersome when there are lots of data to manage. The previous workflow involved finding a property somewhere, context menu on it to
Copy as New Driver, then going back to the constraint and pasting it. Since the data are typically stored in custom properties, this also means
relying on Blender's custom property interfaces which don't offer many organizational features. 

This fork aims to improve some of these issues with the following:

* Added buttons to the constraint panel that displays a context menu
which allow the user to select a suitable constraint target from a user
defined set of objects. 
* Added a new panel that allows the user to select any number of
objects for use by the new driver selection context menu.


When the driver selection menu appears, it will sort all the candidates
alphabetically and for each one, list all the int and float custom
properties that are suitable for use as drivers. Choosing one will
cause any existing driver to be destroyed, and creates a new one using
the selected property.

These features make selecting sources for constraints very efficient
because each sketch can specify which set of source objects to pull data from,
which provides the option to organize dimensional data many useful ways.

I have done only a small amount of testing and while it seems to be
working for me, it may not work for you. 

Possible future enhancements include:
* A global list of driver sources that are shared with all sketches.
* An option to "add" the driver to the existing driver, to facilitate the creation of expressions that use data from multiple driver sources.
* Copy/Paste driver sources between sketches
* Informative tooltips
* Drag & drop the list of driver sources for organizational purposes




![image](https://github.com/ecosky/CAD_Sketcher/assets/8033250/e4c11c37-7508-40c6-925c-2f70b931d2c5)
![image](https://github.com/ecosky/CAD_Sketcher/assets/8033250/6b6da429-9c67-41ad-808c-1567873c5adf)


