# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

from arbiter.utils import pct_agree

def test_pct_agree():
    assert not pct_agree(0.6666, 0, 0)
    assert pct_agree(0.6666, 1, 1)
    assert pct_agree(0.6666, 67, 100)
    assert not pct_agree(0.6666, 66, 100)

    assert pct_agree(0.5, 1, 2)
    assert pct_agree(0.5, 2, 4)
