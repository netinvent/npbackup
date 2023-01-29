## List of features that would be nice to have

- Cube qemu plugin
- Fallback server when primary repo is not available
  - Shall we also include the recent backup job verification ?
    - Example of a bad remote repo path:

      Fatal: unable to open config file: Head "https:/user:***@bad.example.tld/user/config": dial tcp: lookup bad.example.tld: no such host

    - Example of a bad auth:

      Fatal: unable to open config file: unexpected HTTP response (401): 401 Unauthorized
Is there a repository at the following location?

    - Example of a good path, good auth but no repo initialized:

      Fatal: unable to open config file: <config/> does not exist
Is there a repository at the following location?

    - Example: bad password
      
      Fatal: wrong password or no key found

    - Example: non reachable server:

    Fatal: unable to open config file: Head "https://user:***@good.example.tld/user/config": dial tcp [ipv6]:443: connectex: Une tentative de connexion a échoué car le parti connecté n’a pas répondu convenablement au-delà d’une certaine durée ou une connexion établie a échoué car l’hôte de connexion n’a pas répondu.
Is there a repository at the following location?
rest:https://user:***@good.example.tld/user/

- Implement remote upgrade procedure
- Linux installer script
- Windows installer GUI
- Create task from GUI
