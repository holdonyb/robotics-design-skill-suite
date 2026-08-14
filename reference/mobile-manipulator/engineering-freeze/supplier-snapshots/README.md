# Supplier Snapshot Boundary

This directory intentionally contains no vendor datasheet snapshot for the
reference mobile manipulator. Every component in the current reference ledger
is an `engineering_placeholder`; no part is selected, approved for purchase,
or asserted to have a supplier rating.

When external authority permits an engineering review, each candidate part must
have one canonical JSON snapshot containing exact manufacturer, part number,
and reviewed typed limits. The engineering-freeze manifest binds that file by
SHA-256 and records its public source URL and review date. The validator never
downloads a URL, substitutes a family-level rating, or turns a snapshot into a
purchase or motion authorization.
