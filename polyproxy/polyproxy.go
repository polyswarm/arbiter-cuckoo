package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	"golang.org/x/sync/semaphore"
	"gopkg.in/yaml.v2"
)

type Config struct {
	PolyHost string `yaml:"polyswarmd"`
	PolyAuth string `yaml:"apikey"`
	Privkey  string `yaml:"addr_privkey"`
}

type handler struct {
	sync.Mutex
	HomeNonce uint64
	SideNonce uint64
	ps        *Polyswarm
	bc        *Blockchain
}

// Errors we send
type PolyErrorResp struct {
	Status string   `json:"status,omitempty"`
	Errors []string `json:"errors,omitempty"`
}

func mustSign(path string) uint64 {
	switch path {
	case "/staking/deposit":
		return 2
	case "/relay/withdrawal", "/relay/deposit":
		return 1
	}
	if strings.HasPrefix(path, "/bounties/") {
		if strings.HasSuffix(path, "/vote") || strings.HasSuffix(path, "/settle") {
			return 1
		}
	}
	return 0
}

func main() {
	cfg := loadConfig()
	bc, _ := NewBlockchain(cfg.Privkey)

	ps := &Polyswarm{
		semaphore.NewWeighted(32),
		"https://" + cfg.PolyHost,
		cfg.PolyAuth,
		bc.Pubkey(),
	}

	log.Println("Address:", ps.Account)

	h := &handler{
		ps: ps,
		bc: bc,
	}
	if err := h.SyncNonce(); err != nil {
		log.Fatalln("Could not sync nonce:", err)
	}
	go func() {
		for {
			time.Sleep(time.Second * 30)
			h.SyncNonce()
		}
	}()
	s := &http.Server{
		Addr:    "localhost:8001",
		Handler: h,
	}
	log.Fatalln(s.ListenAndServe())
}

func (h *handler) SyncNonce() error {
	h.Lock()
	defer h.Unlock()
	home, err := h.ps.Nonce("home")
	if err == nil && home > h.HomeNonce {
		log.Println("Synced home nonce:", home)
		h.HomeNonce = home
	} else {
		return err
	}
	side, err := h.ps.Nonce("side")
	if err == nil && side > h.SideNonce {
		log.Println("Synced side nonce:", side)
		h.SideNonce = side
	} else {
		return err
	}
	return nil
}

func (h *handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	err := h.handle(w, r)
	if err != nil {
		log.Println("ERROR:", err)
		w.WriteHeader(503)
		e := json.NewEncoder(w)
		e.Encode(PolyErrorResp{
			Status: "FAIL",
			Errors: []string{err.Error()},
		})
	}
}

func (h *handler) handle(w http.ResponseWriter, r *http.Request) error {
	sign := mustSign(r.URL.Path)

	params, err := url.ParseQuery(r.URL.RawQuery)
	if err != nil {
		return err
	}

	if params.Get("account") == "" {
		params.Set("account", h.ps.Account)
	}
	chain := params.Get("chain")
	if sign > 0 {
		if chain != "side" && chain != "home" {
			return fmt.Errorf("Caller must set valid chain parameter")
		}
		h.Lock()
		if chain == "side" {
			params.Set("base_nonce", fmt.Sprintf("%v", h.SideNonce))
			h.SideNonce += sign
		} else {
			params.Set("base_nonce", fmt.Sprintf("%v", h.HomeNonce))
			h.HomeNonce += sign
		}
		h.Unlock()
	}

	u := r.URL.Path + "?" + params.Encode()
	log.Println(sign, u)
	pr, err := h.ps.Request(r.Method, u).Timeout(PolyswarmTimeoutNonTX).Raw()
	if err != nil {
		if pr.statusCode > 0 && len(pr.Errors) > 0 {
			log.Println("API error:", pr.Error())
			// Have a valid API response, proxy it
			w.WriteHeader(pr.statusCode)
			w.Write(pr.raw)
			return nil
		}
		log.Println("Internal API error:", err)
		return err
	}

	if sign == 0 {
		// Non-TX, proxy response
		w.WriteHeader(pr.statusCode)
		w.Write(pr.raw)
		return nil
	}

	// Sign transaction
	var resp struct {
		Transactions []Transaction `json:"transactions"`
	}
	if err := json.Unmarshal(pr.Result, &resp); err != nil {
		pr.decodeErr = err
		return pr
	}
	log.Printf("Transactions: %+v", resp.Transactions)

	signed, err := h.bc.SignTransactions(resp.Transactions)
	if err != nil {
		return pr
	}

	log.Printf("Signed: %v", signed)

	// Send transaction
	req := struct {
		Transactions []string `json:"transactions"`
	}{signed}

	pr, err = h.ps.Request(
		"POST",
		fmt.Sprintf("/transactions?account=%v&chain=%v", h.ps.Account, chain),
	).Timeout(PolyswarmTimeoutTX).JSON(req).Raw()
	if pr.statusCode > 0 && len(pr.raw) > 0 {
		w.WriteHeader(pr.statusCode)
		w.Write(pr.raw)
		return nil
	}
	return err
}

func loadConfig() (cfg Config) {
	if err := unmarshal(os.Args[1], &cfg); err != nil {
		log.Fatalln(err)
	}
	return
}

func unmarshal(fn string, v interface{}) error {
	b, err := ioutil.ReadFile(fn)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(b, v)
}
