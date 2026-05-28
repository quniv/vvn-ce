# Template — do NOT commit real values. Create the secret with:
#
#   kubectl create secret generic vdict-crawler-secret \
#     --namespace vocab \
#     --from-literal=db_url='postgresql+asyncpg://user:pass@host:5432/vocab'
#
# Or apply a sealed-secret / external-secrets equivalent.
apiVersion: v1
kind: Secret
metadata:
  name: vdict-crawler-secret
  namespace: vocab
type: Opaque
stringData:
  db_url: "postgresql+asyncpg://<user>:<password>@<host>:5432/<dbname>"
