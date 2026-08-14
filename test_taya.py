import asyncio

from app.taya.taya_service import taya_service
from app.taya.taya_state_service import (
    taya_state_service,
)
from app.taya.feature_engineering_service import (
    feature_engineering_service,
)
from app.taya.conversation_controller import (
    conversation_controller,
)


# =========================================================
# PRINT STATE
# =========================================================

def print_state(session_id: str):

    state = taya_state_service.get_state(
        session_id
    )

    print("\n" + "=" * 70)
    print("CURRENT TAYA STATE")
    print("=" * 70)

    for field, value in state["data"].items():

        print(
            f"{field:<35}: {value}"
        )

    print("\nMissing fields:")

    missing = (
        taya_state_service.get_missing_fields(
            session_id
        )
    )

    if missing:

        for field in missing:

            print(
                f"  - {field}"
            )

    else:

        print("  NONE")


# =========================================================
# TEST CONVERSATION
# =========================================================

async def main():

    # Use a fixed ID for an easy-to-read test.
    # If your state service persists sessions between runs,
    # change this ID when you want a completely fresh test.
    session_id = "test-taya-001"

    print("=" * 70)
    print("TAYA CONVERSATION TEST")
    print("=" * 70)

    print(
        "\nType 'exit' to stop."
    )

    # -----------------------------------------------------
    # IMPORTANT:
    # The greeting is now owned by ConversationController.
    # test_taya.py only displays it.
    #
    # We no longer hard-code:
    #   "What type of business do you have?"
    #
    # because Taya must ask for language first.
    # -----------------------------------------------------

    print("\nTaya:")

    print(
        conversation_controller.get_greeting()
    )

    # -----------------------------------------------------
    # Conversation loop
    # -----------------------------------------------------

    while True:

        try:

            user_message = input(
                "\nYou: "
            ).strip()

        except KeyboardInterrupt:

            print(
                "\n\nExiting..."
            )

            break

        if not user_message:
            continue

        if user_message.lower() == "exit":
            break

        # -------------------------------------------------
        # Process message
        # -------------------------------------------------

        try:

            result = (
                await taya_service.process_message(
                    session_id=session_id,
                    user_message=user_message,
                )
            )

        except Exception as error:

            print(
                "\nERROR:"
            )

            print(
                type(error).__name__,
                ":",
                error,
            )

            break

        # -------------------------------------------------
        # Taya response
        # -------------------------------------------------

        print("\nTaya:")

        print(
            result["response"]
        )

        # -------------------------------------------------
        # Extraction
        # -------------------------------------------------

        print("\n[Extracted]")

        if result["extracted"]:

            for field, value in (
                result["extracted"].items()
            ):

                print(
                    f"  {field}: {value}"
                )

        else:

            print(
                "  No new information extracted."
            )

        # -------------------------------------------------
        # Missing
        # -------------------------------------------------

        print("\n[Missing fields]")

        missing = result[
            "missing_fields"
        ]

        if missing:

            print(
                ", ".join(missing)
            )

        else:

            print(
                "NONE"
            )

        # -------------------------------------------------
        # Complete
        # -------------------------------------------------

        if result["complete"]:

            print(
                "\n" + "=" * 70
            )

            print(
                "TAYA HAS COLLECTED ALL USER FEATURES"
            )

            print(
                "=" * 70
            )

            # ---------------------------------------------
            # Build model features
            # ---------------------------------------------

            state_data = (
                taya_state_service.get_all_data(
                    session_id
                )
            )

            model_features = (
                feature_engineering_service.build_features(
                    state_data
                )
            )

            missing_model_features = (
                feature_engineering_service
                .get_missing_features(
                    model_features
                )
            )

            print(
                "\n[MODEL FEATURES]"
            )

            for field in (
                feature_engineering_service.MODEL_FEATURES
            ):

                print(
                    f"{field:<35}: "
                    f"{model_features.get(field)}"
                )

            print(
                "\n[MODEL MISSING FEATURES]"
            )

            if missing_model_features:

                for field in missing_model_features:

                    print(
                        f"  - {field}"
                    )

            else:

                print(
                    "NONE"
                )

            if (
                feature_engineering_service
                .is_ready_for_model(
                    model_features
                )
            ):

                print(
                    "\n✅ Features are ready "
                    "for the existing ML model."
                )

            else:

                print(
                    "\n⚠️ Features are NOT ready "
                    "for the ML model."
                )

            break

    print(
        "\nTest finished."
    )


# =========================================================
# ENTRY POINT
# =========================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )