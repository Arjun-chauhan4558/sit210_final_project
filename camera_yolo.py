
import os
import time
import numpy as np
import cv2
import config

picam2 = None
cv_camera = None
ncnn_net = None
last_detection_time = 0.0


def init_camera():
    global picam2, cv_camera

    try:
        from picamera2 import Picamera2

        cam = Picamera2()
        cam_config = cam.create_preview_configuration(
            main={
                "size": (config.CAMERA_WIDTH, config.CAMERA_HEIGHT),
                "format": "RGB888"
            }
        )

        cam.configure(cam_config)
        cam.start()
        time.sleep(1)

        if cam.capture_array() is not None:
            picam2 = cam
            return True, "Camera READY"

    except Exception as e:
        print("Picamera2 error:", e)

    return False, "Camera NOT WORKING"


def init_yolo_model():
    global ncnn_net

    model_dir = os.path.expanduser(config.MODEL_DIR)
    param_file = os.path.join(model_dir, "model.ncnn.param")
    bin_file = os.path.join(model_dir, "model.ncnn.bin")

    if not os.path.exists(param_file) or not os.path.exists(bin_file):
        return False, "Model files not found: " + model_dir

    try:
        import ncnn

        net = ncnn.Net()
        net.opt.use_vulkan_compute = False
        net.opt.num_threads = 4

        net.load_param(param_file)
        net.load_model(bin_file)

        ncnn_net = net
        return True, "YOLO MODEL READY"

    except Exception as e:
        return False, str(e)


def capture_frame():
    global picam2, cv_camera

    if picam2 is not None:
        try:
            rgb = picam2.capture_array()

            if rgb is not None:
                frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                return cv2.rotate(frame, cv2.ROTATE_180)

        except Exception as e:
            print("Camera capture error:", e)

    if cv_camera is not None and cv_camera.isOpened():
        ret, frame = cv_camera.read()

        if ret and frame is not None:
            return cv2.rotate(frame, cv2.ROTATE_180)

    return None


def detect_pothole(frame=None, use_cooldown=True):
    global ncnn_net, last_detection_time

    import ncnn

    if ncnn_net is None:
        return False, 0.0, [], None

    if frame is None:
        frame = capture_frame()

    if frame is None:
        return False, 0.0, [], None

    now = time.time()

    if use_cooldown:
        if now - last_detection_time < config.DETECTION_COOLDOWN_SECONDS:
            return False, 0.0, [], None

    orig_h, orig_w = frame.shape[:2]

    try:
        in_mat = ncnn.Mat.from_pixels_resize(
            frame,
            ncnn.Mat.PixelType.PIXEL_BGR2RGB,
            orig_w,
            orig_h,
            config.MODEL_INPUT_SIZE,
            config.MODEL_INPUT_SIZE
        )

        in_mat.substract_mean_normalize(
            [0.0, 0.0, 0.0],
            [1.0 / 255.0, 1.0 / 255.0, 1.0 / 255.0]
        )

        with ncnn_net.create_extractor() as ex:
            ex.input("in0", in_mat)
            ret_code, out0 = ex.extract("out0")

            if ret_code != 0:
                return False, 0.0, [], None

            out_arr = np.array(out0)

            if out_arr.ndim != 2:
                return False, 0.0, [], None

            if out_arr.shape[0] == 5:
                boxes = out_arr[:4, :]
                scores = out_arr[4, :]
            else:
                boxes = out_arr[:, :4].T
                scores = out_arr[:, 4]

            max_idx = int(np.argmax(scores))
            best_score = float(scores[max_idx])

            if best_score >= config.CONFIDENCE_THRESHOLD:
                cx = float(boxes[0, max_idx])
                cy = float(boxes[1, max_idx])
                w = float(boxes[2, max_idx])
                h = float(boxes[3, max_idx])

                scale_x = orig_w / float(config.MODEL_INPUT_SIZE)
                scale_y = orig_h / float(config.MODEL_INPUT_SIZE)

                xmin = max(0, int((cx - w / 2) * scale_x))
                ymin = max(0, int((cy - h / 2) * scale_y))
                xmax = min(orig_w, int((cx + w / 2) * scale_x))
                ymax = min(orig_h, int((cy + h / 2) * scale_y))

                last_detection_time = now

                _, buf = cv2.imencode(".jpg", frame)

                return (
                    True,
                    round(best_score, 2),
                    [xmin, ymin, xmax, ymax],
                    buf.tobytes()
                )

    except Exception as e:
        print("Detection error:", e)

    return False, 0.0, [], None


def release_camera():
    global picam2, cv_camera

    if picam2 is not None:
        try:
            picam2.stop()
            picam2.close()
        except Exception:
            pass

    if cv_camera is not None:
        cv_camera.release()


if __name__ == "__main__":
    try:
        print("Starting camera...")
        camera_ok, camera_message = init_camera()
        print(camera_message)

        if not camera_ok:
            raise RuntimeError("Camera could not start")

        print("Loading your trained YOLO model...")
        model_ok, model_message = init_yolo_model()
        print(model_message)

        if not model_ok:
            raise RuntimeError(model_message)

        print("LIVE POTHOLE DETECTION STARTED")
        print("Press Q to quit")

        while True:
            frame = capture_frame()

            if frame is None:
                continue

            detected, confidence, bbox, image = detect_pothole(
                frame,
                use_cooldown=False
            )

            if detected:
                x1, y1, x2, y2 = bbox

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    (0, 255, 0),
                    2
                )

                cv2.putText(
                    frame,
                    f"POTHOLE {confidence:.2f}",
                    (x1, max(25, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2
                )

            else:
                cv2.putText(
                    frame,
                    "No pothole detected",
                    (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2
                )

            cv2.imshow("Pothole Detection System - YOLO26n", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except Exception as e:
        print("ERROR:", e)

    finally:
        release_camera()
        cv2.destroyAllWindows()
        print("Camera stopped")
