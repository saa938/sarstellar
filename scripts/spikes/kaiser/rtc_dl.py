import json, sys, os, logging, time
import earthaccess
logging.getLogger("earthaccess").setLevel(logging.ERROR)
rows=json.load(open(sys.argv[1])); out=sys.argv[2]; want=sys.argv[3].split(",")  # e.g. T115:20260713,T115:20260911
urls=[u for r in rows for w in want if r["burst"].startswith(w.split(":")[0]) and r["date"]==w.split(":")[1] for u in r["urls"]]
print(len(urls), "files")
earthaccess.login(strategy="netrc", persist=False)
t=time.time(); files=earthaccess.download(urls, local_path=out, show_progress=False)
print(len(files), "downloaded in", round(time.time()-t,1), "s; total MB", round(sum(os.path.getsize(f) for f in files)/1e6,1))
