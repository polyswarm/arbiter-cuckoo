# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

from arbiter.abstracts import (
    Bounty, Address, Artifact, EventQueue, Verdict, Assertion
)

def test_address():
    assert Address(1) == 1
    assert Address(1) != 2
    assert Address(0x11) == 17
    assert Address("0x1234") == 0x1234
    assert Address("0xf00") == Address(0xf00)
    assert str(Address(0)) == "0x0000000000000000000000000000000000000000"
    assert "%s" % Address(0x234) == "0x0000000000000000000000000000000000000234"

def test_artifact():
    assert Artifact("abcd") == "abcd"
    assert Artifact("foo") != Artifact("bar")
    assert Artifact("baz") == Artifact("baz")

def test_verdict():
    assert Verdict("1", [True]) != Verdict("0", [True])
    assert Verdict("1", [True]) != Verdict("1", [False])
    assert Verdict("1", [True]) == Verdict("1", [True])
    assert Verdict("0", [False]) == Verdict("0", [False])

def test_assertion():
    assert Assertion.from_dict({
        "author": 1, "bid": 2, "mask": 3, "metadata": 4, "verdicts": 5,
    }) == Assertion(None, 1, None, 2, 3, 4, 5)

def test_bounty():
    b = Bounty.from_dict({
        "amount": "62500000000000000",
        "author": "0xAF8302a3786A35abEDdF19758067adc9a23597e5",
        "expiration": "4603",
        "guid": "fd44e5eb-8a62-470e-beff-0dc06a156ec2",
        "resolved": False,
        "uri": "3fmmtg",
        "verdicts": [
            False
        ],
    })
    assert b.amount == 62500000000000000
    assert b.author == Address(0xAF8302a3786A35abEDdF19758067adc9a23597e5)
    assert b.expiration == 4603
    assert b.guid == "fd44e5eb-8a62-470e-beff-0dc06a156ec2"
    assert b.resolved is False
    assert b.uri == "3fmmtg"
    assert b.verdicts == [False]

    assert b == Bounty(
        amount=62500000000000000,
        author=0xAF8302a3786A35abEDdF19758067adc9a23597e5,
        expiration=4603,
        guid="fd44e5eb-8a62-470e-beff-0dc06a156ec2",
        resolved=False,
        uri=Artifact("3fmmtg"),
        verdicts=[False],
    )

def test_queue():
    q = EventQueue()

    q.push_bounty({
        "amount": "62500000000000000",
        "author": "0xD6625a8A1A8a3BDB953d20A9310333D362b137DA",
        "expiration": 1614,
        "guid": "eeb50c1c-8114-4060-b82e-963d501c9fb4",
        "resolved": False,
        "uri": "hello",
        "verdicts": [
            False
        ],
    })
    q.push_assertion({
        "bounty_guid": "eeb50c1c-8114-4060-b82e-963d501c9fb4",
        "author": "0x1f50Cf288b5d19a55ac4c6514e5bA6a704BD03EC",
        "index": 0,
        "bid": "625000000000000000",
        "mask": [
            True,
        ],
        "metadata": "assert1!",
        "verdicts": [
            True,
        ],
    })
    q.push_assertion({
        "bounty_guid": "eeb50c1c-8114-4060-b82e-963d501c9fb4",
        "author": "0xc6514e5bA6a704BD03EC1f50Cf288b5d19a55ac4",
        "index": 1,
        "bid": "625000000000000000",
        "mask": [
            True,
        ],
        "metadata": "assert2!",
        "verdicts": [
            False,
        ]
    })

    assert list(q.bounties.keys()) == ["eeb50c1c-8114-4060-b82e-963d501c9fb4"]
    assert list(q.bounties.values()) == [Bounty(
        62500000000000000, 0xD6625a8A1A8a3BDB953d20A9310333D362b137DA, 1614,
        "eeb50c1c-8114-4060-b82e-963d501c9fb4", False, "hello", [False], [
            Assertion(
                "eeb50c1c-8114-4060-b82e-963d501c9fb4",
                0x1f50Cf288b5d19a55ac4c6514e5bA6a704BD03EC,
                0, 625000000000000000, [True], "assert1!", [True],
            ),
            Assertion(
                "eeb50c1c-8114-4060-b82e-963d501c9fb4",
                0xc6514e5bA6a704BD03EC1f50Cf288b5d19a55ac4,
                1, 625000000000000000, [True], "assert2!", [False],
            ),
        ]
    )]
