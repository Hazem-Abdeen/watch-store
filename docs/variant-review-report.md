**Variant review — proposal for approval**

Based solely on the existing `import-data/variant-analysis.json` (rule version 1). No database access, imports, product regrouping, or conversion code. The only new artifact is this report. Specifications below are source claims, not independently verified manufacturer specifications.

**Whole-file totals**

731 products analyzed; 77 candidate groups containing 198 distinct products; 34 ambiguous groups; 450 products ungrouped; 0 excluded. Ambiguous groups can overlap.

| Measure | Candidate groups (77) | Ambiguous groups (34), for context |
|---|---:|---:|
| Identical child prices | 74 | 19 |
| Different child prices | 3 | 15 |
| Missing child prices | 0 | 0 |
| Complete matching core specifications, with a color difference | 77 | 14 |
| Any recorded size/material/core conflict | 0 | 17 |

“Color only” concerns product specifications, excluding SKU, title, image, and commercial price differences. All six core fields (gender, movement, case size, case material, band material, water resistance) are present and match within every candidate; other recorded non-color specifications also match. Thus 74 candidates differ only by color with equal prices, and 3 differ by color plus price. Price comparisons use numeric JOD values. Material aliases such as St.Steel are treated as Stainless Steel.

The three candidates with different prices are Casio GBD-200 (180/163 JOD), Jaguar J893 (336/351 JOD), and Santa Barbara Polo SB.1.10657 (88/94/94 JOD).

Among ambiguous groups, conflict counts overlap: case size 13; band material 2; water resistance 5; gender 2; movement 0; case material 0. These preserve the existing analysis classification: one water-resistance conflict is only `3ATM` versus `3 ATM` (SB.1.10552). It should not be counted as a substantive rating difference after approved normalization.

**10 high-confidence candidates from all seven available brands**

“High confidence” below preserves the file’s classification, not automatic-conversion approval. Of all 77 candidates, only 12 have family evidence in every child’s SKU; 65 have at least one child supported only by an explicit model token in its title. Under the proposed stricter rules, those 65 need model verification. An explicit title model code is useful evidence, but does not independently validate a barcode SKU.

Prices are JOD. SS = Stainless Steel, including St.Steel/ST.Steel spellings. Q = the source movement label “Analog Quartz (Battery)”. Shared specifications apply to every child in that group. Color spelling/capitalization is retained. Water-resistance wording such as “(Diving)” is copied from the source, not endorsed as a usage recommendation.

**C1. Proposed parent: CASIO GBD-200 — Brand: Casio**

Movement: Analog Quartz (Battery) / Power Saving (Display goes blank to save power 3 hours everyday.); Case size: 53 mm; Water resistance: 200-meter.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| GBD-200-1DR | CASIO G-SHOCK G-SQUAD GBD-200-1DR | 180 | Black | Black / Resin | Black / Resin |
| GBD-200-9DR | CASIO G-SHOCK G-SQUAD GBD-200-9DR | 163 | Black | Lime Green / Resin | Lime Green / Resin |

Grouped because: exact parsed family `GBD-200` from SKU references and explicit model tokens in titles, all six matching core fields, and distinct band color/case color options. Meets the recorded-data identity/specification gates; automatic use still requires an approved brand-specific suffix rule.

**C2. Proposed parent: CASIO MTP-1375D — Brand: Casio**

Movement: Q; Case size: 43 mm; Water resistance: 5 BAR.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| MTP-1375D-3AVDF | CASIO MTP-1375D-3AVDF FOR MEN | 56 | Green | Silver / SS | Silver / SS |
| MTP-1375D-7A2VDF | CASIO MTP-1375D-7A2VDF FOR MEN | 56 | Gray | Silver / SS | Silver / SS |

Grouped because: exact parsed family `MTP-1375D` from SKU references and explicit model tokens in titles, all six matching core fields, and distinct dial color options. Meets the recorded-data identity/specification gates; automatic use still requires an approved brand-specific suffix rule.

**C3. Proposed parent: DANIEL KLEIN DK.1.13938 — Brand: Daniel Klein**

Movement: Q; Case size: 35 mm; Water resistance: 5 BAR.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| 8682308327045 | DANIEL KLEIN DK.1.13938-4 WOMEN WATCH | 43 | Silver | Gold / SS | Gold / SS |
| 8682308327052 | DANIEL KLEIN DK.1.13938-5 WOMEN WATCH | 43 | Silver | Silver & Gold / SS | Silver / SS |

Grouped because: exact parsed family `DK.1.13938` from explicit model tokens in titles, all six matching core fields, and distinct band color/case color options. Proposed MANUAL REVIEW until the title model references are corroborated by structured/manufacturer identity data.

**C4. Proposed parent: DANIEL KLEIN DK.1.14266 — Brand: Daniel Klein**

Movement: Automatic; Case size: 43 mm; Water resistance: 5 BAR.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| 8682308442212 | DANIEL KLEIN DK.1.14266-2 MEN WATCH | 107 | Black | Silver / SS | Silver / SS |
| 8682308442229 | DANIEL KLEIN DK.1.14266-3 MEN WATCH | 107 | Green | Silver& Gold / SS | Silver / SS |

Grouped because: exact parsed family `DK.1.14266` from explicit model tokens in titles, all six matching core fields, and distinct dial color/band color options. Proposed MANUAL REVIEW until the title model references are corroborated by structured/manufacturer identity data.

**C5. Proposed parent: FREELOOK FL.1.10410 — Brand: FreeLook**

Movement: Q; Case size: 35 mm; Water resistance: 3 ATM.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| FL.1.10410-1 | FREELOOK FL.1.10410-1 | 73 | Silver | Silver / SS | Silver / SS |
| FL.1.10410-2 | FREELOOK FL.1.10410-2 | 73 | Silver | Gold / SS | Gold / SS |

Grouped because: exact parsed family `FL.1.10410` from SKU references and explicit model tokens in titles, all six matching core fields, and distinct band color/case color options. Meets the recorded-data identity/specification gates; automatic use still requires an approved brand-specific suffix rule.

**C6. Proposed parent: JAGUAR J1024 — Brand: Jaguar**

Movement: Q; Case size: 44 mm; Water resistance: 10 Bar (Diving).

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| J1024/1 | JAGUAR RC, BLUE DIAL WATCH J1024/1 | 269 | Blue | Silver / SS | Silver / SS |
| J1024/2 | JAGUAR RC GREEN DIAL WATCH J1024/2 | 269 | Green | Silver / SS | Silver / SS |
| J1024/3 | JAGUAR RC, BLACK DIAL WATCH J1024/3 | 269 | Black | Silver / SS | Silver / SS |

Grouped because: exact parsed family `J1024` from SKU references and explicit model tokens in titles, all six matching core fields, and distinct dial color options. Meets the recorded-data identity/specification gates; automatic use still requires an approved brand-specific suffix rule.

**C7. Proposed parent: JAGUAR J893 — Brand: Jaguar**

Movement: Q; Case size: 34.5 mm; Water resistance: 20 Bar (Diving).

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| J893/1 | JAGUAR EXECUTIVE DAME WHITE DIAL J893/1 | 336 | White | Silver & Gold / SS | Gold / SS |
| J893/3 | JAGUAR EXECUTIVE DAME WATCH J893/3 | 351 | Green | Gold & Silver / SS | Gold & Silver / SS |

Grouped because: exact parsed family `J893` from SKU references and explicit model tokens in titles, all six matching core fields, and distinct dial color/case color options. Meets the recorded-data identity/specification gates; automatic use still requires an approved brand-specific suffix rule.

**C8. Proposed parent: LOTUS 18886 — Brand: Lotus**

Movement: Q; Case size: 31.5 mm; Water resistance: 5 Bar (Diving).

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| 18886/3 | LOTUS SILVER & GOLD ST.STEEL FOR WOMEN | 102 | Blue | Silver & Gold / SS | Gold / SS |
| 18886/4 | LOTUS SILVER & GOLD WITH BLACK DIAL ST.STEEL FOR WOMEN | 102 | Black | Silver & Gold / SS | Gold / SS |

Grouped because: exact parsed family `18886` from SKU references, all six matching core fields, and distinct dial color options. Meets the recorded-data identity/specification gates; automatic use still requires an approved brand-specific suffix rule.

**C9. Proposed parent: SANTA BARBARA POLO SB.1.10650 — Brand: Santa Barbara Polo**

Movement: Automatic; Case size: 47 mm; Water resistance: 3 ATM.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| 8682308355376 | SANTA BARBARA POLO SB.1.10650-2 MEN WATCH | 162 | Black | Black / Leather | Black / SS |
| 8682308355390 | SANTA BARBARA POLO SB.1.10650-4 MEN WATCH | 162 | Black | Black / Leather | Gold / SS |

Grouped because: exact parsed family `SB.1.10650` from explicit model tokens in titles, all six matching core fields, and distinct case color options. Proposed MANUAL REVIEW until the title model references are corroborated by structured/manufacturer identity data.

**C10. Proposed parent: VALENTINO ORLANDI VO.1.10015 — Brand: Valentino Orlandi**

Movement: Q; Case size: 45 mm; Water resistance: 5 ATM.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| 8682308347678 | VALENTINO ORLANDI VO.1.10015-3 MEN WATCHES | 184 | Green | Green / Rubber | Grey / SS |
| 8682308347692 | VALENTINO ORLANDI VO.1.10015-5 MEN WATCHES | 184 | Black | Black / Rubber | Grey / SS |

Grouped because: exact parsed family `VO.1.10015` from explicit model tokens in titles, all six matching core fields, and distinct dial color/band color options. Proposed MANUAL REVIEW until the title model references are corroborated by structured/manufacturer identity data.

**10 ambiguous groups**

Parent names here are review labels, not approved parents.

**A1. Proposed parent: CASIO EFR-571DC — Brand: Casio**

Movement: Q; Water resistance: 10 BAR.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material | Case size |
| --- | --- | --- | --- | --- | --- | --- |
| EFR-571DC-1AVUDF | CASIO EDIFICE Standard Chronograph EFR-571DC-1AVUDF | 135 | Black | Black / SS | Green / SS | 44 mm |
| EFR-571DC-2AVUDF | CASIO EDIFICE Standard Chronograph EFR-571DC-2AVUDF | 135 | Blue | Black / SS | Black / SS | 45 mm |

Grouped because: the analyzer parsed family `EFR-571DC` from SKU references and explicit model tokens in titles.

Ambiguous because: Case size conflicts: 44 versus 45 mm. Do not treat the 1 mm difference as rounding without evidence.

**A2. Proposed parent: CASIO MTD-135D — Brand: Casio**

Movement: Q; Water resistance: 5 BAR.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material | Case size |
| --- | --- | --- | --- | --- | --- | --- |
| MTD-135D-2AVDF | CASIO MTD-135D-2AVDF FOR MEN | 75 | Blue | Silver / SS | Silver / SS | 43 mm |
| MTD-135D-3AVDF | CASIO MTD-135D-3AVDF FOR MEN | 75 | Green | Silver / SS | Silver / SS | 43 mm |
| MTD-135D-7AVDF | CASIO MTD-135D-7AVDF FOR MEN | 75 | White | Silver / SS | Silver / SS | 43 mm |
| MTD-135D-7AVDF-1 | CASIO MTP-1215A-7ADF FOR MEN | 41 | White | Silver / SS | Silver / SS | 41 mm |

Grouped because: the analyzer parsed family `MTD-135D` from SKU references and explicit model tokens in titles.

Ambiguous because: The copy-like SKU MTD-135D-7AVDF-1 has a title naming MTP-1215A, a 41 mm case instead of 43 mm, and the same recorded color combination as MTD-135D-7AVDF. It also appears in the next group; do not merge the two families transitively.

**A3. Proposed parent: CASIO MTP-1215A — Brand: Casio**

Movement: Q.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material | Case size | Water resistance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MTD-135D-7AVDF-1 | CASIO MTP-1215A-7ADF FOR MEN | 41 | White | Silver / SS | Silver / SS | 41 mm | 5 BAR |
| MTP-1215A-7ADF | CASIO LTP-V001GL-1BUDF FOR WOMEN | 30 | Gold | Brown / Leather | Gold / SS | 31 mm | 3 ATM |

Grouped because: the analyzer parsed family `MTP-1215A` from explicit model tokens in titles and SKU references.

Ambiguous because: Both children have SKU/title identity contradictions. MTD-135D-7AVDF-1 names MTP-1215A in its title; MTP-1215A-7ADF names LTP-V001GL in its title. Gender is Men versus Women; size, band material, and water resistance also conflict. The first child overlaps the preceding group.

**A4. Proposed parent: DANIEL KLEIN DK.1.13951 — Brand: Daniel Klein**

Movement: Q; Case size: 35 mm; Water resistance: 5 BAR.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| 8682308327694-682308327695 | DANIEL KLEIN DK.1.13951-2 WOMEN WATCH | 42 | Silver | Gold / SS | Gold / SS |
| 8682308327793 | DANIEL KLEIN DK.1.13951-2 WOMEN WATCH | 43 | Silver | Gold / SS | Gold / SS |

Grouped because: the analyzer parsed family `DK.1.13951` from explicit model tokens in titles.

Ambiguous because: Both titles name the exact same DK.1.13951-2 reference and all recorded options are identical, despite different SKUs and prices. Possible duplicate listings; price is not an option.

**A5. Proposed parent: FREELOOK FL.1.10401 — Brand: FreeLook**

Movement: Q; Water resistance: 3 ATM.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material | Case size |
| --- | --- | --- | --- | --- | --- | --- |
| FL.1.10401-4 | FREELOOK FL.1.10401-4 | 89 | White | Silver & Gold / SS | Silver / SS | 32 mm |
| FL.1.10401-5 | FREELOOK FL.1.10401-5 | 89 | White | Silver & Rose gold / SS | Silver / SS | 25 mm |

Grouped because: the analyzer parsed family `FL.1.10401` from SKU references and explicit model tokens in titles.

Ambiguous because: Case size conflicts: 32 versus 25 mm. Shared family and differing band colors do not override the size conflict.

**A6. Proposed parent: JAGUAR J1025 — Brand: Jaguar**

Movement: Q.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material | Case size | Water resistance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| J1025/1 | JAGUAR RC, GREEN DIAL WATCH J1025/1 | 400 | Blue | Silver / SS | Silver / SS | 44 mm | 10 Bar (Diving) |
| J1025/2 | JAGUAR RC, GREEN DIAL WATCH J1025/2 | 400 | Green | Silver / SS | Silver / SS | 44 mm | 10 Bar (Diving) |
| J1025/3 | JAGUAR RC, BLACK DIAL WATCH J1025/3 | 400 | Black | Silver / SS | Silver / SS | 43 mm | 5 Bar (Diving) |

Grouped because: the analyzer parsed family `J1025` from SKU references and explicit model tokens in titles.

Ambiguous because: Case size is 44 versus 43 mm; water resistance is 10 versus 5 Bar. J1025/1 says GREEN DIAL in its title but records Blue. Resolve both core and option conflicts.

**A7. Proposed parent: LOTUS 18851 — Brand: Lotus**

Movement: Q; Case size: 37.5 mm.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material | Water resistance |
| --- | --- | --- | --- | --- | --- | --- |
| 18851/3 | LOTUS GREEN & GREEN DIAL LEATHER FOR MEN | 88 | Green | Green / SS | Silver / SS | 5 Bar (Diving) |
| 18851/3-1 | LOTUS BLACK LEATHER FOR MEN | 117 | Black | Black / Leather | Black / SS | 10 Bar (Diving) |

Grouped because: the analyzer parsed family `18851` from SKU references.

Ambiguous because: Band material differs (steel versus leather), water resistance differs (5 versus 10 Bar), and 18851/3-1 is copy-like. Additionally, 18851/3 says LEATHER in its title but records a steel band.

**A8. Proposed parent: SANTA BARBARA POLO SB.1.10552 — Brand: Santa Barbara Polo**

Movement: Q; Case size: 34 mm.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material | Water resistance |
| --- | --- | --- | --- | --- | --- | --- |
| SB.1.10552-2 | SANTA BARBARA POLO & RACQUET CLUB SB.1.10552-2 | 76 | White | Gold / SS | Gold / SS | 3 ATM |
| SB.1.10552-3 | SANTA BARBARA POLO & RACQUET CLUB SB.1.10552-3 | 81 | White | silver & gold / SS | silver / SS | 3ATM |

Grouped because: the analyzer parsed family `SB.1.10552` from SKU references and explicit model tokens in titles.

Ambiguous because: The analyzer flags 3 ATM versus 3ATM. This is a spacing-only difference, not a different stated rating. Approved normalization can remove this flag; retain the different child prices. Reassess under all other rules before conversion.

**A9. Proposed parent: VALENTINO ORLANDI VO.1.10008 — Brand: Valentino Orlandi**

Movement: Q; Case size: 45 mm; Water resistance: 5 ATM.

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| 8682308347319 | VALENTINO ORLANDI VO.1.10008-2 MEN WATCHES | 184 | Black | Gold / SS | Gold / SS |
| 8682308347326 | VALENTINO ORLANDI VO.1.10008-3 MEN WATCHES | 184 | Green | Silver & Gold / SS | Silver / SS |

Grouped because: the analyzer parsed family `VO.1.10008` from explicit model tokens in titles.

Ambiguous because: SKU 8682308347319 is structured as Women but its title says MEN; the analyzer also flags a description/attribute gender contradiction. The other child is Men. Model-family evidence comes only from title tokens.

**A10. Proposed parent: LOTUS chrono — Brand: Lotus**

Movement: Q; Case size: 42 mm; Water resistance: 10 Bar (Diving).

| Child SKU | Child title | JOD | Dial color | Band color / material | Case color / material |
| --- | --- | --- | --- | --- | --- |
| 18690/2-1-2 | LOTUS SILVER CHRONO STAINLESS STEEL WATCH BRACELET FOR MEN | 83 | Black | Silver / SS | Silver / SS |
| 18690/2-1-2-2 | LOTUS BLUE CHRONO STAINLESS STEEL WATCH BRACELET FOR MEN | 83 | Blue | Silver / SS | Silver / SS |

Grouped because: the analyzer matched the normalized title “chrono”, matching recorded core fields, and differing dial colors.

Ambiguous because: Only a normalized generic title matches; there is no accepted explicit family identifier. Both SKUs have copy-like suffix chains. Keep independent unless a reliable source establishes actual model identities; never strip these suffixes to manufacture a family.

**Proposed strict rules**

**AUTO VARIANT — every condition must pass**

1. Same single verified brand and exact model family, backed for every child by structured manufacturer/model data or a genuine SKU/MPN using an approved brand-specific family/suffix convention. Preserve collection, gender, material and model-revision components. No arbitrary truncation, barcode-prefix inference, copy-suffix stripping, or title-only identity. Matching brand or similar titles never suffice.
2. All children have complete, equal movement, case size, case material, band material, water resistance, and compatible verified gender. Compare all other available functional specifications too (for example caliber, chronograph, solar power or connectivity); conflicts block automatic grouping. Missing core values are unknown, never matches. Agreement in copied source values does not prove factual accuracy.
3. Normalize only approved equivalences: case/spacing, Gray/Grey, unambiguous steel abbreviations, order of a two-color combination, mm whitespace, and identical water-rating units with spacing differences such as 3ATM/3 ATM. Never round sizes, collapse movement types, infer material from color, or discard meaningful rating qualifiers. Cross-unit rating conversions need an explicitly approved mapping.
4. Differences are restricted to verified dial/band/case colors or cosmetic finishes that do not alter material or specifications. Every child has a complete, unique selectable option combination and a unique nonempty SKU/model-option identity. Resolve title/attribute contradictions, duplicate-looking records and all overlapping families first. Each child belongs to exactly one approved parent; never merge groups transitively.
5. Prices may differ and do not establish family identity. Keep each child’s original SKU, price/currency, stock/stockrecords and applicable images/specifications. The proposed Oscar parent is the family container; child products remain the individual purchasable options. Product-class and existing parent/child compatibility must be checked separately before any future conversion; this report has not inspected Oscar state.

**MANUAL REVIEW**

Route any plausible family here if identity is title-token-only, references disagree, suffix semantics are uncertain, a core field is missing/conflicting, descriptions/titles contradict attributes, option combinations collide, SKUs look copied, or memberships overlap. Size, movement, case material, band material and genuine water-resistance differences block AUTO. Verify manufacturer/source evidence; correct source errors or split the family, then reassess. A verified cosmetic spelling/spacing difference may be normalized without changing the original source artifact. No automatic salvage of a subset while unresolved family identity could change its membership.

**STANDALONE**

Keep products independent when there is no reliable shared model-family evidence; matches are only brand, generic title, price or barcode prefix; verified references identify different models; or verified size/material/movement/water-resistance differences represent distinct products under this color-only policy. Products without a real distinguishing variant option must not become artificial children. Suspected duplicates stay unchanged pending a separate duplicate review. The 450 currently ungrouped products remain standalone unless new explicit evidence is found; this is not proof that none can ever have variants.

**Rules proposed for your approval**

Approve automatic grouping only for verified exact-family color variants with complete matching core specifications and unique child options. Send uncertain identity, missing/conflicting specifications and duplicates to manual review. Keep unsupported matches and verified distinct models standalone. Retain child-specific prices. The existing 77 candidates are not a blanket conversion list: 65 need title-reference verification; the remaining 12 pass the recorded identity/specification gates but still require approval of the SKU conventions and later Oscar-state checks. Approval here is for these rules only; imports and conversion remain separate work.

Source SHA-256: `0fbaa4799524381c6cb80ab850199f1cd4e5ce9aebcf4b28a536c9e2adce57c4`.
