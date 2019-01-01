package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"golang.org/x/sync/semaphore"
	"gopkg.in/yaml.v2"
)

const NONCE_SYNC_INTERVAL = time.Second * 20
const MAX_NONCE_ROLLBACKS = 3

type Config struct {
	PolyHost string `yaml:"polyswarmd"`
	PolyAuth string `yaml:"apikey"`
	Privkey  string `yaml:"addr_privkey"`
}

type Chain struct {
	Name               string
	Nonce              uint64
	MinedNonce         uint64
	NonceRollbackCount uint64
}

type handler struct {
	sync.Mutex
	Home Chain
	Side Chain
	ps   *Polyswarm
	bc   *Blockchain
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

func (c *Chain) SyncNonce(n uint64) {
	if n > c.Nonce {
		log.Println("ERROR: Forward", c.Name, "nonce:", n)
		c.Nonce = n
		c.NonceRollbackCount = 0
	} else if n != c.Nonce && c.MinedNonce == n {
		c.NonceRollbackCount++
		if c.NonceRollbackCount > 1 {
			log.Println("ERROR: No mining progress on", c.Name, " nonce:", n, "internal:", c.Nonce)
		}
		if c.NonceRollbackCount >= MAX_NONCE_ROLLBACKS {
			log.Println("ERROR: Rollback", c.Name, "; nonce:", n)
			c.Nonce = n
			c.NonceRollbackCount = 0
		}
	} else {
		c.NonceRollbackCount = 0
	}
	c.MinedNonce = n
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
	h.Home.Name = "home"
	h.Side.Name = "side"
	if err := h.SyncNonce(); err != nil {
		log.Fatalln("ERROR: Could not sync nonce:", err)
	}
	go func() {
		for {
			time.Sleep(NONCE_SYNC_INTERVAL)
			if err := h.SyncNonce(); err != nil {
				log.Println("ERROR: Could not sync nonce:", err)
			}
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
	if err == nil {
		h.Home.SyncNonce(home)
	} else {
		return err
	}
	side, err := h.ps.Nonce("side")
	if err == nil {
		h.Side.SyncNonce(side)
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
	params := r.URL.Query()

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
			params.Set("base_nonce", fmt.Sprintf("%v", h.Side.Nonce))
			h.Side.Nonce += sign
		} else {
			params.Set("base_nonce", fmt.Sprintf("%v", h.Home.Nonce))
			h.Home.Nonce += sign
		}
		h.Unlock()
	}

	u := r.URL.Path + "?" + params.Encode()
	preq := h.ps.Request(r.Method, u).Timeout(PolyswarmTimeoutNonTX)
	// Proxy body, if it exists
	if r.ContentLength != 0 {
		ct := r.Header.Get("Content-Type")
		if ct == "" {
			ct = "application/json; charset=utf8"
		}
		preq.req.Header.Set("Content-Type", ct)
		preq.req.Body = r.Body
		preq.req.ContentLength = r.ContentLength
	}
	// Directly proxy if not a signing request
	proxy := w
	if sign > 0 {
		proxy = nil
	}
	s := time.Now()
	pr, err := preq.Raw(proxy)
	log.Println(sign, r.Method, u, r.ContentLength, time.Since(s))
	if err != nil {
		return err
	}
	if pr.statusCode != 200 || len(pr.Errors) > 0 {
		log.Println("ERROR:", pr.statusCode, nows(string(pr.raw)))
	}
	if sign == 0 {
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

	signed, err := h.bc.SignTransactions(resp.Transactions)
	if err != nil {
		return err
	}

	// Send transaction
	req := struct {
		Transactions []string `json:"transactions"`
	}{signed}

	s = time.Now()
	pr, err = h.ps.Request(
		"POST",
		fmt.Sprintf("/transactions?account=%v&chain=%v", h.ps.Account, chain),
	).Timeout(PolyswarmTimeoutTX).JSON(req).Raw(w)
	log.Println(sign, r.Method, u, r.ContentLength, "SIGN", time.Since(s))

	if pr.statusCode > 0 && len(pr.raw) > 0 {
		if pr.statusCode != 200 {
			log.Println("ERROR: Transaction status:", nows(string(pr.raw)))
		}
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

func nows(s string) string {
	return strings.Trim(s, " \t\r\n")
}
