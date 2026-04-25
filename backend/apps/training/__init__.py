"""apps.training — offline training stack (picks #41-46).

Each sub-package wraps a single training-time concern:

- ``optim/`` — pick #41 L-BFGS-B (Byrd, Lu, Nocedal, Zhu 1995)
- ``hpo/`` — pick #42 TPE (Bergstra et al. 2011 NeurIPS)
- ``schedule/`` — pick #43 Cosine Annealing (Loshchilov & Hutter 2017 ICLR)
- ``loss/`` — pick #44 LambdaLoss (Wang et al. 2018 CIKM)
- ``avg/`` — pick #45 SWA (Izmailov et al. 2018 NeurIPS)
- ``sample/`` — pick #46 OHEM (Shrivastava et al. 2016 CVPR)

Per the Anti-Spaghetti Charter (plan §"Architecture Principles"),
this app is the single sanctioned new-app exception in the
completion phase: the offline training stack is a coherent layer
that didn't fit into the existing apps.pipeline.services or
apps.sources homes. Each sub-package stays small and reuses the
existing helpers wherever possible — no parallel implementations.
"""
