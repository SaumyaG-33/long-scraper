"""
The question this whole project is about: does height actually change fit
outcome? Hold everything else constant, vary height, and see what the model
— trained on 190K+ real fit-feedback reviews — actually says.

    python -m fit_model.demo
"""
from fit_model.predict import predict_fit

HEIGHTS = [
    (58, "4'10\""), (62, "5'2\""), (65, "5'5\""), (68, "5'8\""),
    (71, "5'11\""), (74, "6'2\""), (77, "6'5\""),
]

# A few categories where length/proportion plausibly matters most.
CATEGORIES = ["gown", "jumpsuit", "maxi", "romper", "dress"]


def main():
    for category in CATEGORIES:
        print(f"\n=== category={category!r}, size=8, weight=135lbs, body_type=hourglass ===")
        print(f"{'height':<10} {'small':>8} {'fit':>8} {'large':>8}")
        for height_in, label in HEIGHTS:
            probs = predict_fit(
                height_in=height_in, weight_lbs=135, body_type="hourglass",
                category=category, size=8,
            )
            print(f"{label:<10} {probs.get('small', 0):>8.3f} {probs.get('fit', 0):>8.3f} {probs.get('large', 0):>8.3f}")


if __name__ == "__main__":
    main()
