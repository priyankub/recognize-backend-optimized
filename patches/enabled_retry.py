"""Patch recognize_backend main.py: the app checks once at startup whether Nextcloud has it enabled. nc_py_api's
enabled_state returns False on any error, so if Nextcloud is not up yet (common after a host reboot) the worker waits
forever: Nextcloud already considers the app enabled and never calls /enabled again. While not enabled, ask Nextcloud
again every minute. Fails the build if upstream changed."""
import sys
p = sys.argv[1]
s = open(p).read()
old = '''        while not ENABLED.is_set():
            sleep(5)
'''
new = '''        waited = 0
        while not ENABLED.is_set():
            sleep(5)
            waited += 5
            if waited % 60 == 0 and nc.enabled_state:
                LOGGER.info("Nextcloud reports the app as enabled, starting the worker")
                ENABLED.set()
'''
if s.count(old) != 1:
    sys.exit("enabled_retry patch: anchor not found exactly once")
open(p, "w").write(s.replace(old, new))
print("enabled_retry patch applied")
