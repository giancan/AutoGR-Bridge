# AutoGR Bridge

A QGIS plugin that connects [AutoGR-Toolkit](https://github.com/giancan/AutoGR-Toolkit) to QGIS for automatic image georeferencing.

Select a reference raster (or a canvas snapshot), add your dataset images, choose a feature descriptor, and click **Run**. AutoGR-SIFT launches automatically, and when processing finishes the georeferenced results are imported back into your QGIS project.

You can find the latest version, you can visit the [official QGIS Plugin page](https://plugins.qgis.org/plugins/AutoGR_Bridge/) or directly from your QGIS.

---

## Requirements

- **QGIS 3.22** or later
- **AutoGR-Toolkit v6.0 or later** — [download here](https://github.com/giancan/AutoGR-Toolkit)
  - Deep learning descriptors (SuperGLUE, LoFTR, DISK, ALIKE-D) require the **64-bit** version

---

## Installation

1. Download `AutoGR_Bridge-6.1.zip` from the [Releases](https://github.com/giancan/AutoGR-Bridge/releases) page.
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

---

## Supported Descriptors

SIFT, ASIFT, SURF, AKAZE, KAZE, FAST-FREAK, ORB, BRISK, SuperGLUE, LoFTR, DISK, ALIKE-D+LightGlue

---

## License

GNU General Public License v2.0 — see [LICENSE](LICENSE).

## Author

Gianluca Cantoro — [gianluca.cantoro@gmail.com](mailto:gianluca.cantoro@gmail.com)
