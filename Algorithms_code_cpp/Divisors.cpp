vector<long long int> Divisors(long long int n){ 
    vector<long long int> loc;
    for (long long int i=1; i<=sqrt(n); i++){ 
        if (n%i == 0){ 
            if (n/i == i) loc.pb(i); 
            else loc.pb(i),loc.pb(n/i);
        } 
    } 
    return loc;
} 
