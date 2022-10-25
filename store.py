import json
from pathlib import Path
from typing import Dict
from starsessions import SessionStore, Serializer


SESSIONS_DIR = Path(".sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


#class FSStoreSerializer(Serializer):
#
#    def serialize(self, data: typing.Any) -> bytes:
#        return json.dumps(data).encode('utf-8')
#
#    def deserialize(self, data: bytes) -> typing.Dict[str, typing.Any]:
#        return json.loads(data)


 
class FilesystemStore(SessionStore):

    #def __init__(self):
    #    self._storage = {}

    def session_file(self, session_id):
        return SESSIONS_DIR / session_id

    async def read(self, session_id: str, lifetime: int) -> Dict:
        """ Read session data from a data source using session_id. """
        #return self._storage.get(session_id, {})
        f = self.session_file(session_id)
        try:
            if f.exists():
                return json.load(f.open())
        except OSError: # happens if a lingering session cookie from Starlette's builtin sessions results in filename too long
            pass
        return {}

    async def write(self, session_id: str, data: Dict, lifetime: int, ttl: int) -> str:
        """ Write session data into data source and return session id. """
        json.dump(data.decode("utf-8"), self.session_file(session_id).open("w"))
        #self._storage[session_id] = data
        return session_id

    async def remove(self, session_id: str):
        """ Remove session data. """
        #del self._storage[session_id]
        self.session_file(session_id).unlink()

    async def exists(self, session_id: str) -> bool:
        #return session_id in self._storage
        return self.session_file(session_id).exists()
