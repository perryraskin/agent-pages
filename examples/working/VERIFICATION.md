# Working-state gallery verification

Verified with the repository's real web renderer and synthetic workshop fixture.
The existing showcase PNG and `server/page_work.py` remain unchanged.

- `npm run build`, `npm test`: protocol test and 47 Python tests passed, including
  10 status/history tests and the existing private live/previous API route tests.
- `npm run test:form`: existing hydrated form interaction passed.
- `npm run capture:working`: real revision polling, content reveal, author caret,
  changed-text overlays, done/caret removal, settled highlights and reload passed.
  Checked 390 × 844 and 1440 × 1000 viewports, plus reduced motion.
- Browser inspection independently observed the mobile cursor beside the changed
  paragraph and the completed desktop status with the cursor hidden and no overflow.
- `python3 examples/working/verify.py`: gallery size/dimensions, PNG CRCs and metadata,
  README/example local links, and original showcase preservation passed.
- Browser tests reject external requests and identifying visible text. Only synthetic
  workshop content and the fictional agent Aster appear in the captures. No native
  Messages UI, recipient, account, private library, credential or host is pictured.

[Mobile content reveal](https://cdn.upfile.sh/NgkqPlXzzq.png): actual 390px web viewport,
with the agent flag at the last changed paragraph.

[Desktop content reveal](https://cdn.upfile.sh/nXMyFyeue7.png): actual 1440px web viewport,
with the same revision, status and cursor.

[Three-state gallery](https://cdn.upfile.sh/XYdQjjbWJq.png): working, revealed content,
and completed state in matching decorative frames.

These checks establish the web behavior only. Native iMessage delivery, physical
devices, and production agent integration were not exercised. Snapshot images cannot
convey animation; the browser regression checks the transitions themselves. Real
clock times and installed fonts mean rerenders need not be pixel-identical.
