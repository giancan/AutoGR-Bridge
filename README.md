# AutoGR Bridge

A QGIS plugin that connects [AutoGR-Toolkit](https://github.com/giancan/AutoGR-Toolkit) to QGIS for automatic image georeferencing.

Select a reference raster (or a canvas snapshot), add your dataset images, choose a feature descriptor, and click **Run**. AutoGR-SIFT launches automatically, and when processing finishes the georeferenced results are imported back into your QGIS project.

---

## Requirements

- **QGIS 3.22 or later**, including **QGIS 4**
- **AutoGR-Toolkit v7.0 or later** — [download here](https://github.com/giancan/AutoGR-Toolkit)
  - Deep learning descriptors (SuperGLUE, LoFTR, DISK, ALIKE-D, SuperPoint) require the **64-bit** version

---

## Installation

1. Download `AutoGR_Bridge-7.0.0.zip` from the [Releases](https://github.com/giancan/AutoGR-Bridge/releases) page.
2. In QGIS, go to **Plugins → Manage and Install Plugins → Install from ZIP**.
3. Browse to the downloaded zip and click **Install Plugin**.
4. The plugin appears in the **AutoGR** menu and in the toolbar.

---

## Usage

1. Open a QGIS project with a georeferenced raster layer (or have a map canvas ready).
2. Click the **AutoGR-Bridge** toolbar button.
3. Set the path to `01-AutoGR_SIFT.exe` (inside your AutoGR-Toolkit installation folder).
4. Choose a **Base image**: either a raster layer from the project or a canvas snapshot.
5. Add one or more **dataset images** to georeference.
6. Choose a **Descriptor** and **Matcher**, adjust subsampling and rotation if needed.
7. Set an **Output folder** where results will be saved.
8. Click **Run**.

Results are automatically imported into the QGIS project as raster layers when processing finishes.

### Overlay preview (optional)

Click **Overlay on map...** next to the dataset list to place a photo semi-transparently on the map before matching: drag it, scale it (slider, typed percentage or corner handles) and rotate it, then apply the rotation to the bridge. The base image can be cropped to the photo's footprint.

For historical aerial photos, the optional **Photo / mission data** box sizes the overlay from film format, flying height and focal length, and draws a sun-shadow arrow from the date and time to help with orientation. Any one of format, height and focal length can be worked out from the other two with **Guess**, as can the time from a shadow you can see.

---

## Supported Descriptors

The list is read from the linked AutoGR-SIFT, so it always matches the installed toolkit — for example SIFT, RootSIFT, ASIFT, SURF, AKAZE, KAZE, FAST-FREAK, ORB, BRISK, SuperGLUE, LoFTR, DISK, ALIKE-D+LightGlue and SuperPoint.

---

## License

GNU General Public License v2.0 — see [LICENSE](LICENSE).

## Author

Gianluca Cantoro — [gianluca.cantoro@gmail.com](mailto:gianluca.cantoro@gmail.com)
