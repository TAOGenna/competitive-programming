lli min_ops(vector<lli> v){
   lli n=sz(v);
   lli mid = v[n/2],mid1 = v[(n/2)-1];
   lli res = 0,res1 = 0;
   for(lli i=0;i<n;i++){
	res = res + abs(v[i] - mid);
	res1 = res1 +abs(v[i] - mid1);
   }
   return min(res,res1);
}
