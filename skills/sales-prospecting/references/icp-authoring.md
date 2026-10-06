# Writing a segment (ICP) file

Save as `./sales-workspace/icp/<CODE>.yaml` (your folder overrides bundled examples with the same code).
Start from `assets/icp-template.yaml`. Interview checklist, ask the user:
1. Who exactly is the ideal customer, and what pain do they have (observable on the public web)?
2. Which businesses to exclude (too big, government, competitors, wrong specialty)? Size limits?
3. Who decides, and what titles? Is the owner visible publicly?
4. Which first offer will you make (never a price)? What proof exists (only real, citable results)?
5. Which channel first (whatsapp, instagram, email, linkedin)?
6. Which countries and cities, which sources (maps, registries, chambers, directories, socials)?

Required keys: `code, name, description, specialties, exclusions, fit_signals, search_hints, channel_order, first_offer`.
Optional: `team_noun, team_noun_large, min_team, max_team, max_branches, discover_priority, large_hint,
decision_maker, decision_maker_titles, source_hints`. Query templates may use `{city}` and `{country}`.
Keep offers and signals free of price words; the loader's tests enforce this for bundled examples.
