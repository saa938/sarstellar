import logging, earthaccess
logging.getLogger("earthaccess").setLevel(logging.ERROR)
def https_fs():
    auth = earthaccess.login(strategy="netrc", persist=False)
    assert auth.authenticated, "EDL login failed"
    return earthaccess.get_fsspec_https_session()
def gcov_url(ur, coll):
    return f"https://nisar.asf.earthdatacloud.nasa.gov/NISAR/{coll}/{ur}/{ur}.h5"
