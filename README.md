# napari-TopoStats

[![License MIT](https://img.shields.io/pypi/l/napari-loadafm.svg?color=green)](https://github.com/MaxGamill-Sheffield/napari-loadafm/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/napari-loadafm.svg?color=green)](https://pypi.org/project/napari-loadafm)
[![Python Version](https://img.shields.io/pypi/pyversions/napari-loadafm.svg?color=green)](https://python.org)
[![tests](https://github.com/MaxGamill-Sheffield/napari-loadafm/workflows/tests/badge.svg)](https://github.com/MaxGamill-Sheffield/napari-loadafm/actions)
[![codecov](https://codecov.io/gh/MaxGamill-Sheffield/napari-loadafm/branch/main/graph/badge.svg)](https://codecov.io/gh/MaxGamill-Sheffield/napari-loadafm)
[![napari hub](https://img.shields.io/endpoint?url=https://api.napari-hub.org/shields/napari-loadafm)](https://napari-hub.org/plugins/napari-loadafm)

----------------------------------

This [napari] plugin was generated with [Cookiecutter] using the [cookiecutter-napari-plugin] template.

<!--
Don't miss the full getting started guide to set up your new package:
https://github.com/napari/cookiecutter-napari-plugin#getting-started

and review the napari docs for plugin developers:
https://napari.org/stable/plugins/index.html
-->

## Installation

Activate your Python environment (e.g. Conda) and make sure your Python version is >= 3.10 and < 3.12. An example
conda enviroment command would be:

    conda create -n napari-env python=3.11
    conda activate napari-env

With [Git installed] on your machine, install the napari-TopoStats package from GitHub using [pip][pip].

    pip install git+https://github.com/AFM-SPM/napari-TopoStats.git@main

This command will install other required modules from GitHub (AFMReader, napari-AFMReader, TopoStats)

You can then run napari with:

    napari

## Usage

To load an image into the napari viewer, drag and drop your image file into the window.
A small window will open prompting you to input the input channel for the image you are loading.
Enter the channel used by your image (e.g. Height). The loaded image will appear as a layer in the GUI.
Note: this loading utility comes from [napari-AFMReader].

<img src="readme_images/input_channel_window.png" width="800" alt="Input channel window"/>

Topostats tools can be accessed from the toolbar of napari (top left) as shown.

<img src="readme_images/toolbar.png" width="800" alt="Toolbar"/>

This will then open a window containing buttons with available functions.
Select a layer, then click the button corresponding to the function you want to run on the layer.

<img src="readme_images/button_grid.png" width="800" alt="Button Grid"/>

Before running the function, you can choose to load a config file using the button and selecting the file.
Both json and yaml file formats are supported.
This config will be used for the functions you run until you close napari.
There is also a button to save that file as the new default (instead of the topostats generated one). This default can
be reset to the topostats default at anytime by clicking the Reset Default Config button in the bottom right
of the main window.

<img src="readme_images/config_file.png" width="800" alt="Loading a config file"/>

When you run a function which requires the config, if you haven't loaded a config file manually, a default
configuration is used which will be the config you have set as default if you have set one. If you haven't, the
topostats default will be used.
Once a config is loaded, either manually or automatically, an edit config button will appear, which opens a window
allowing the config file to be edited directly through the napari gui. Changes made are not automatically saved
to the loaded config file, however, the updated config file can be saved as a file with the Save to file button
at the bottom of the window. In this window, there is also a button to save the edited config file as the new default.

<img src="readme_images/edit_config_window.png" width="800" alt="Edit config window"/>

When you run a function for the first time, a window will open with options to adjust for that function
(which are applied next time the function is run) if that function has options which can be adjusted.
There is also a run button in that window. This runs the function on the selected layer (it does exactly the
same thing as clicking the function button in the grid). Note this window will only appear if there are options which
can be adjusted outside of those in the config file.

<img src="readme_images/function_window.png" width="800" alt="Function window"/>

**Batch Process** is a special function that works the same as if running `topostats process` in the command line,
using the config you currently have loaded or the default config (with adjusted options if you have updated your
default) if you haven't loaded a config. If the default is used, a window will appear asking you to select a directory
which contains the data to be processed as well as a directory to save the output files to (which you may want to
create with the new folder button if the directory doesn't exist). Otherwise, the directories defined in the config
file will be used. Once these have been defined topostats will process in the background (the output and progress
can been seen in the command line). You can carry on using napari while this happens.
<img src="readme_images/batch_process.png" width="800" alt="Function window"/>

Current functions:

1. Load config button allows a config file to be selected from your hard disk.
2. Run filters requires an image layer to be selected and creates an image layer with topostats filters run.
3. Run grains requires an image layer to be selected and creates a labels layer with topostats grains detection run.
4. Make 3D requires an image layer to be selected and creates a 3D image layer. Viewing mode (in the bottom left of
the viewer) is automatically switched to 3D.
5. Run Grainstats requires a labels layer **created by the Run Grains function** to be selected and creates an
interactivate table in the dock on the right.
6. Batch process uses the full topostats pipeline to process a directory of files. View above for details.

## Contributing

Contributions are very welcome. Tests can be run with [tox], please ensure
the coverage at least stays the same before you submit a pull request.

## License

Distributed under the terms of the [MIT] license,
"napari-topostats" is free and open source software

## Issues

If you encounter any problems, please [file an issue] along with a detailed description.

[napari-AFMReader]: https://github.com/AFM-SPM/napari-AFMReader
[Cookiecutter]: https://github.com/audreyr/cookiecutter
[Git installed]: https://git-scm.com/book/en/v2/Getting-Started-Installing-Git
[MIT]: http://opensource.org/licenses/MIT
[cookiecutter-napari-plugin]: https://github.com/napari/cookiecutter-napari-plugin
[napari]: https://github.com/napari/napari
[pip]: <https://pypi.org/project/pip/>
[tox]: https://tox.readthedocs.io/en/latest/
[file an issue]: https://github.com/AFM-SPM/napari-TopoStats/issues
