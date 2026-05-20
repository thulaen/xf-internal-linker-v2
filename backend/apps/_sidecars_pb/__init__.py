# quality-debt-ignore: reason: this package's _pb2.py and _pb2_grpc.py stubs
# were generated alongside the slice-1.6 introduction commit of
# services/sidecars/api/*.proto. The hook check-stubs-not-regenerated.py
# treats them as derived artefacts that must move only when the contract
# moves; on this commit BOTH the contract files (services/sidecars/api/)
# AND the generated stubs are staged together. The hook does not pair
# Python stubs under backend/apps/_sidecars_pb/ to Go-tier api/ contracts
# automatically (its pairing logic looks for sibling api.proto only). This
# waiver is the documented escape for that one-time discovery. After this
# commit lands, future regenerations track the contract changes via the
# Go-tier path which the hook DOES pair.
