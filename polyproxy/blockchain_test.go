package main

import (
	"encoding/json"
	"os"
	"testing"
)

func TestSign(t *testing.T) {
	privkey := os.Getenv("PRIVKEY")
	rawtx := []byte(`{"chainId": 1338,"data":"0x5592d6870000000000000000000000000000000031880eb58681425a93a6c777d15b636e","gas":5000000,` +
		`"gasPrice":0,"value":0,"to":"0x2048eDA0128dFE81332aeA4e877d3b3E61D898E9","nonce":16462}`)

	var tx Transaction
	json.Unmarshal(rawtx, &tx)
	t.Logf("TX: %+v:", tx)

	bc, _ := NewBlockchain(privkey)
	signed, err := bc.SignTransactions([]Transaction{tx})
	if err != nil {
		t.Fatalf("Failed to sign: %v", err)
	}
	// XXX: does not work
	expect := "f88882404e80834c4b40942048eda0128dfe81332aea4e877d3b3e61d89" +
		"8e980a45592d6870000000000000000000000000000000031880eb58681425a93a6" +
		"c777d15b636e820a97a041664a0bec3b5837d2e14ca27b1568a481be7fe5f4ae9cb" +
		"957c09458effa608ea00c80c79f0efcb9dd71b7bcef570db3ad6d3cf7bb6cb421fa" +
		"106bb9396d31ef6a"
	if signed[0] != expect {
		t.Logf("Need: %v", expect)
		t.Logf("Got:  %v", signed[0])
		t.Fatalf("Bad signature value")
	}
}
