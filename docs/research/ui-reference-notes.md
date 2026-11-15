# Scientific interface references

Reviewed 2026-11-15 using official documentation and interface descriptions:

- [ASF Vertex user manual](https://docs.asf.alaska.edu/vertex/manual/)
- [NASA Worldview](https://worldview.earthdata.nasa.gov/) and its official comparison controls
- [Copernicus Browser documentation](https://documentation.dataspace.copernicus.eu/Applications/Browser.html)

These tools organize work around location, dataset, acquisition dates, map layers and selected
results. ASF describes a results list linked to scene details and available files; metadata such
as time, orbit and polarization remains attached to the selected scene. Copernicus separates
search/visualization parameters, the central map and tools. Its search results expose basic
metadata before full details. Worldview maintains explicit A/B layer and date choices during
comparison, rather than relying on an unlabeled visual split.

SARstellar adopts that hierarchy: the map remains the working surface, cases and acquisition
context belong near selection, and a selected area leads to evidence and exports. The benchmark
now starts with a short outcome, followed by the primary fusion comparison and labeled evaluation
counts. The sample exclusions and reference limitations remain visible. Pooled per-class results
are the default; land-cover details remain available through the existing filter. Supervised
fusion stays separate from the unsupervised comparison, with matched training controls.

The Methods page uses Data, Processing, Validation and Limits sections. Acquisition constraints,
block units, statistical thresholds and validation scope appear before optional implementation
disclosures. Longer references and supporting explanations use disclosure controls. No scores,
scientific data or statistical calculations were changed for this interface revision.

Restrained chrome, compact typography and limiting strong colors to data/selection are our design
inferences, not requirements imposed by those tools. Light and dark previews support the same
workflow; neither theme is treated as the user's choice until selected. We reuse the principles
of these applications rather than claiming to reproduce their full features or exact appearance.
