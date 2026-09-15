# Phase 2.5 workbook -> complaints.json change log

Source: `UrduCX_Phase2_5_Authoring_Workbook.docx` (human-authored).
All complaint text is the maintainer's. No variant was machine-written.

## Applied globally

- Stripped Unicode bidi control characters (Word artifacts, invisible).
- Collapsed runs of whitespace to single spaces.
- Removed the `[...]` field wrappers from the workbook template.

## Content edits (maintainer-approved)

- Case 01 / code_switched: 'aik hafte pehle' -> 'aik mah pehle' (approved edit)
- Case 10 / english: appended 'The transaction ID is TXN 512.' (approved edit)
- Case 15 / english: 'Someone from Jazz called me today and asked for OTP and PIN around 3 PM' -> 'Someone called me today around 3 PM claiming to be a Jazz representative and asked for OTP and PIN' (approved edit)

## Stray-character removals

- Case 02 / roman_urdu: removed stray leading 'آ'
- Case 03 / urdu_script: removed stray leading 'م['
- Case 03 / roman_urdu: removed stray leading 'م'
- Case 19 / english: removed stray leading 'د'

## fact_span

All 80 `fact_span` values were replaced with an exact contiguous substring of their own variant text. The workbook versions were summaries or keyword lists (e.g. `UPAISA, 10000, 6PM`) and could not satisfy the validator or serve as T3 gold spans. No complaint text was altered to make a span fit.
