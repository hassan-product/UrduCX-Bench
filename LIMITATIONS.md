# Limitations

The first release is expected to have several important limitations:

- A single primary annotator may introduce systematic judgment bias.
- App-store reviews overrepresent negative experiences and users willing to post publicly.
- Public evaluation splits can be incorporated into future model training data.
- Telecom and mobile-wallet language does not represent all Urdu customer-service settings.
- Text-only evaluation does not measure speech recognition or spoken interaction quality.
- Roman Urdu spelling varies heavily by region, dialect, and individual practice.
- PII redaction uses typed patterns and explicit self-identification phrases rather than general
	name detection. Names or identifiers written in unexpected forms may remain and require manual
	review before release or external processing.

Measured limitations, annotation agreement, exclusions, and known dataset skews will be added before
the first benchmark release.
