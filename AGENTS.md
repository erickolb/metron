# Experimental branch instructions

- The CPHTest notetaker is temporary. Before creating or merging any upstream PR,
  STOP if `python scripts/check_upstream_experiment.py` fails. Tell Eric the
  temporary recorder must be removed first, even if he forgets this requirement.
- Remove the notetaker route/module/settings, its client feedback submission code,
  and any feedback data from the proposed upstream change. Preserve research data
  privately outside Git. Disabling the endpoint is not sufficient for upstream.
- Do not merge or submit upstream with the notetaker present. The upstream-removal
  CI check intentionally fails on PRs to master while this temporary code exists.
