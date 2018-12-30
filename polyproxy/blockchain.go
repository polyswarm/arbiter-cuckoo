package main

import (
	"bytes"
	"crypto/ecdsa"
	"encoding/hex"
	"math/big"

	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
	"github.com/ethereum/go-ethereum/crypto"
)

type Transaction struct {
	ChainID  int      `json:"chainId"`
	Data     string   `json:"data"`
	GasLimit uint64   `json:"gas"`
	GasPrice *big.Int `json:"gasPrice"`
	Value    *big.Int `json:"value"`
	Nonce    uint64   `json:"nonce"`
	To       string   `json:"to"`
}

type Blockchain struct {
	Privkey *ecdsa.PrivateKey
}

func NewBlockchain(key string) (*Blockchain, error) {
	privkey, err := crypto.HexToECDSA(noex(key))
	if err != nil {
		return nil, err
	}
	return &Blockchain{privkey}, nil
}

func (b *Blockchain) Pubkey() string {
	pub := b.Privkey.Public().(*ecdsa.PublicKey)
	addr := crypto.PubkeyToAddress(*pub)
	return addr.Hex()
}

func (b *Blockchain) SignTransactions(txs []Transaction) ([]string, error) {
	var signed []string
	for _, tx := range txs {
		data, err := hex.DecodeString(noex(tx.Data))
		if err != nil {
			return nil, err
		}
		chainid := new(big.Int)
		chainid.SetInt64(int64(tx.ChainID))
		s := types.NewEIP155Signer(chainid)

		t, err := types.SignTx(types.NewTransaction(
			tx.Nonce,
			common.HexToAddress(tx.To),
			tx.Value,
			tx.GasLimit,
			tx.GasPrice,
			data,
		), s, b.Privkey)
		if err != nil {
			return nil, err
		}
		var b bytes.Buffer
		if err := t.EncodeRLP(&b); err != nil {
			return nil, err
		}
		signed = append(signed, hex.EncodeToString(b.Bytes()))
	}
	return signed, nil
}

func noex(s string) string {
	if s[:2] == "0x" {
		return s[2:]
	}
	return s
}
