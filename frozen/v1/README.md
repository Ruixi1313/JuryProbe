# JuryProbe v1 Frozen Artifacts

This directory records the frozen v1 source frame and the first pool-based
Entity N=300 construction artifacts.

Artifact type: `pool_freeze`. Stage: `construction`. Pool manifests, build
manifests, and evaluation manifests are tracked separately.

Do not overwrite v1 artifacts. If pool filters, corruption prompts, validators,
post-filters, or sampling rules change, create a new versioned artifact
(`v2`, `v3`, ...). Main paper results should state which frozen version they use.

Frozen v1 includes:

- FEVER master claim pool
- Number / Entity / Relation family pools
- Pool manifest and attrition counts
- Entity pool-v1 N=300 dataset
- Entity construction attempt log
- Entity construction manifest
