import numpy as np, json, os, sys
H=os.path.dirname(os.path.abspath(__file__)); B=np.load(os.path.join(H,"blocks.npz"))
f=B["forest"]; ref=f&(B["f_dist"]>=0.5)
L=B["dHV"]-np.nanmedian(B["dHV"][f]); C=B["T137_dVH"]-np.nanmedian(B["T137_dVH"][f]); Cv=B["T137_dVV"]-np.nanmedian(B["T137_dVV"][f])
ok=f&np.isfinite(L)&np.isfinite(C)
out={}
for nm,a in (("L_dHV",L),("C_dVH",C),("C_dVV",Cv)):
    for t in (-2,-3,-4,-5):
        fl=ok&(a<=t); out[f"{nm}<={t}"]=dict(flags=int(fl.sum()),hits=int((fl&ref).sum()),recall_pct=round(100*(fl&ref).sum()/ref.sum(),1),precision_pct=round(100*(fl&ref).sum()/max(fl.sum(),1),1))
# equal flag count: C threshold that yields same number of flags as L<=-3
n=int((ok&(L<=-3)).sum()); thrC=np.sort(C[ok])[n-1]; fl=ok&(C<=thrC)
out["C_dVH_at_equal_flag_count"]=dict(threshold=round(float(thrC),2),flags=int(fl.sum()),hits=int((fl&ref).sum()))
both=ok&(L<=-3)&(C<=-2); onlyL=ok&(L<=-3)&~(C<=-2)
out["L<=-3_only_not_C<=-2"]=dict(n=int(onlyL.sum()),DIST_hits=int((onlyL&ref).sum()))
out["DIST_ref_blocks"]=int(ref.sum()); out["DIST_missed_by_both(L<=-3,C<=-2)"]=int((ref&ok&~(L<=-3)&~(C<=-2)).sum())
for k,v in out.items(): print(k,v)
s=json.load(open(os.path.join(H,"stats.json"))); s["threshold_sweep_vs_DIST"]=out; json.dump(s,open(os.path.join(H,"stats.json"),"w"),indent=1,default=str)
