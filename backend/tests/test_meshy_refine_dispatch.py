from unittest.mock import patch
from uuid import UUID
from fastapi import HTTPException
import pytest
from nexus.meshy_refine_dispatch import dispatch,inspect,REFINE_COST

RID=UUID("00000000-0000-0000-0000-000000000001")

def test_disabled_by_default_before_network_or_db():
    with patch.dict("os.environ",{},clear=True),patch("nexus.meshy_refine_dispatch.owner",return_value={"id":"owner"}),patch("nexus.meshy_refine_dispatch.balance") as balance,patch("nexus.meshy_refine_dispatch.connection") as db:
        with pytest.raises(HTTPException) as error:
            dispatch(RID,None)
        assert error.value.status_code==503
        balance.assert_not_called()
        db.assert_not_called()

def test_no_key_rejected_before_db():
    with patch.dict("os.environ",{"NEXUS_MESHY_VERIFIED_REFINE_COST":"10"}),patch("nexus.meshy_refine_dispatch.owner",return_value={"id":"owner"}),patch("nexus.meshy_refine_dispatch._key",return_value=""),patch("nexus.meshy_refine_dispatch.connection") as db:
        with pytest.raises(HTTPException) as error:
            dispatch(RID,None)
        assert error.value.status_code==503
        db.assert_not_called()

def test_cost_and_payload_contract():
    assert REFINE_COST==10
    from nexus.meshy_refine_dispatch import ENDPOINT
    assert ENDPOINT=="https://api.meshy.ai/openapi/v2/text-to-3d"
