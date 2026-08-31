// SPDX-License-Identifier: GPL-2.0
/*
 * pico_fan_hwmon.c - Driver virtuale HWMON per ventola USB Raspberry Pi Pico
 * ============================================================================
 * Registra un dispositivo hwmon denominato "pico_fan" che espone via sysfs:
 *
 *   fan1_input  (hwmon_fan_input)  - RPM ventola esterna (scritto dal demone)
 *   pwm1        (hwmon_pwm_input)  - Duty cycle 0-255   (scritto dal demone)
 *
 * Compatibilità kernel:
 *   - Linux 5.6+  : API hwmon_chip_info / hwmon_ops (non deprecated)
 *   - Linux 6.x   : idem
 *   - Linux 7.x   : idem  (devm_hwmon_device_register_with_groups è deprecated
 *                          già da ~6.6; questa implementazione NON la usa)
 *
 * La macro PICO_REMOVE_RET gestisce il cambio di firma di
 * platform_driver.remove avvenuto in Linux 6.11 (da int a void).
 *
 * Autore: pico-fan-control project
 * Versione: 1.0.0
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/version.h>
#include <linux/platform_device.h>
#include <linux/hwmon.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/err.h>

/*
 * Compatibilità firma platform_driver.remove:
 *   < 6.11  → int  (deve fare return 0)
 *   >= 6.11 → void (nessun return value)
 */
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 11, 0)
# define PICO_REMOVE_RET  void
# define PICO_RETURN_OK
#else
# define PICO_REMOVE_RET  int
# define PICO_RETURN_OK   return 0;
#endif

#define DRIVER_NAME    "pico_fan"
#define DRIVER_VERSION "1.0.0"

/* -------------------------------------------------------------------------
 * Struttura dati privata del driver
 * ---------------------------------------------------------------------- */
struct pico_fan_data {
    struct mutex lock;
    long         fan1_rpm;       /* RPM ventola esterna, scritto dal demone  */
    u32          pwm1_duty;      /* Duty cycle 0..255, scritto dal demone    */
    bool         connected;      /* true = Pico USB connesso                  */
};

/* =========================================================================
 * hwmon_ops: is_visible, read, write
 *
 * L'API hwmon_chip_info richiede che is_visible, read e write siano
 * implementate; il framework hwmon gestisce autonomamente le chiamate sysfs.
 * ====================================================================== */

static umode_t pico_fan_is_visible(const void *data,
                                   enum hwmon_sensor_types type,
                                   u32 attr, int channel)
{
    switch (type) {
    case hwmon_fan:
        /* fan1_input: lettura per userspace (lm-sensors),
         * scrittura per il demone (aggiorna RPM da USB)         */
        if (attr == hwmon_fan_input)
            return 0644;
        break;

    case hwmon_pwm:
        /* pwm1: lettura/scrittura                               */
        if (attr == hwmon_pwm_input)
            return 0644;
        break;

    default:
        break;
    }
    return 0;
}

static int pico_fan_read(struct device *dev,
                         enum hwmon_sensor_types type,
                         u32 attr, int channel, long *val)
{
    struct pico_fan_data *data = dev_get_drvdata(dev);

    mutex_lock(&data->lock);

    switch (type) {
    case hwmon_fan:
        if (attr == hwmon_fan_input) {
            *val = data->connected ? data->fan1_rpm : 0;
            mutex_unlock(&data->lock);
            return 0;
        }
        break;

    case hwmon_pwm:
        if (attr == hwmon_pwm_input) {
            *val = data->connected ? (long)data->pwm1_duty : 0;
            mutex_unlock(&data->lock);
            return 0;
        }
        break;

    default:
        break;
    }

    mutex_unlock(&data->lock);
    return -EOPNOTSUPP;
}

static int pico_fan_write(struct device *dev,
                          enum hwmon_sensor_types type,
                          u32 attr, int channel, long val)
{
    struct pico_fan_data *data = dev_get_drvdata(dev);

    mutex_lock(&data->lock);

    switch (type) {
    case hwmon_fan:
        if (attr == hwmon_fan_input) {
            if (val < 0) {
                mutex_unlock(&data->lock);
                return -EINVAL;
            }
            data->fan1_rpm = val;
            mutex_unlock(&data->lock);
            return 0;
        }
        break;

    case hwmon_pwm:
        if (attr == hwmon_pwm_input) {
            if (val < 0 || val > 255) {
                mutex_unlock(&data->lock);
                return -EINVAL;
            }
            data->pwm1_duty = (u32)val;
            mutex_unlock(&data->lock);
            return 0;
        }
        break;

    default:
        break;
    }

    mutex_unlock(&data->lock);
    return -EOPNOTSUPP;
}

static const struct hwmon_ops pico_fan_hwmon_ops = {
    .is_visible = pico_fan_is_visible,
    .read       = pico_fan_read,
    .write      = pico_fan_write,
};

/* =========================================================================
 * Canali hwmon: fan1_input + pwm1
 * ====================================================================== */

static const u32 pico_fan_fan_config[] = {
    HWMON_F_INPUT,
    0,
};

static const u32 pico_fan_pwm_config[] = {
    HWMON_PWM_INPUT,
    0,
};

static const struct hwmon_channel_info pico_fan_fan_channel = {
    .type   = hwmon_fan,
    .config = pico_fan_fan_config,
};

static const struct hwmon_channel_info pico_fan_pwm_channel = {
    .type   = hwmon_pwm,
    .config = pico_fan_pwm_config,
};

static const struct hwmon_channel_info * const pico_fan_info[] = {
    &pico_fan_fan_channel,
    &pico_fan_pwm_channel,
    NULL,
};

static const struct hwmon_chip_info pico_fan_chip_info = {
    .ops  = &pico_fan_hwmon_ops,
    .info = pico_fan_info,
};

/* =========================================================================
 * Attributo extra: fan1_connected  (sysfs raw, non parte dell'API hwmon)
 *
 * Il demone lo usa per segnalare se il Pico è connesso o meno.
 * Esposto in /sys/bus/platform/devices/pico_fan.0/fan1_connected
 * ====================================================================== */

static ssize_t fan1_connected_show(struct device *dev,
                                   struct device_attribute *attr, char *buf)
{
    struct pico_fan_data *data = dev_get_drvdata(dev);
    int val;

    mutex_lock(&data->lock);
    val = data->connected ? 1 : 0;
    mutex_unlock(&data->lock);

    return sysfs_emit(buf, "%d\n", val);
}

static ssize_t fan1_connected_store(struct device *dev,
                                    struct device_attribute *attr,
                                    const char *buf, size_t count)
{
    struct pico_fan_data *data = dev_get_drvdata(dev);
    unsigned long val;
    int ret;

    ret = kstrtoul(buf, 10, &val);
    if (ret)
        return ret;

    mutex_lock(&data->lock);
    data->connected = (val != 0);
    /* Quando si disconnette, azzera i valori visualizzati */
    if (!data->connected) {
        data->fan1_rpm  = 0;
        data->pwm1_duty = 0;
    }
    mutex_unlock(&data->lock);

    return count;
}

static DEVICE_ATTR_RW(fan1_connected);

static struct attribute *pico_fan_extra_attrs[] = {
    &dev_attr_fan1_connected.attr,
    NULL,
};

static const struct attribute_group pico_fan_extra_group = {
    .attrs = pico_fan_extra_attrs,
};

/* =========================================================================
 * Platform Device e Driver
 * ====================================================================== */
static struct platform_device *pico_fan_pdev;

static int pico_fan_probe(struct platform_device *pdev)
{
    struct pico_fan_data *data;
    struct device *hwmon_dev;
    int ret;

    data = devm_kzalloc(&pdev->dev, sizeof(*data), GFP_KERNEL);
    if (!data)
        return -ENOMEM;

    mutex_init(&data->lock);
    data->fan1_rpm  = 0;
    data->pwm1_duty = 0;
    data->connected = false;

    /*
     * Usa devm_hwmon_device_register_with_info() — API moderna,
     * non deprecata su kernel 5.6 → 7.x.
     * Il quarto argomento (drvdata) viene restituito da dev_get_drvdata()
     * nei callback hwmon_ops.
     */
    hwmon_dev = devm_hwmon_device_register_with_info(
        &pdev->dev,
        DRIVER_NAME,
        data,
        &pico_fan_chip_info,
        NULL    /* extra_info groups: non usati qui */
    );

    if (IS_ERR(hwmon_dev)) {
        dev_err(&pdev->dev,
                "Errore registrazione hwmon: %ld\n", PTR_ERR(hwmon_dev));
        return PTR_ERR(hwmon_dev);
    }

    /* Aggiunge l'attributo fan1_connected al platform device (non hwmon) */
    ret = sysfs_create_group(&pdev->dev.kobj, &pico_fan_extra_group);
    if (ret) {
        dev_warn(&pdev->dev,
                 "Impossibile creare attributo fan1_connected: %d\n", ret);
        /* Non fatale: il driver funziona ugualmente */
    }

    platform_set_drvdata(pdev, data);

    dev_info(&pdev->dev,
             "pico_fan hwmon registrato: %s (fan1_input + pwm1)\n",
             dev_name(hwmon_dev));
    return 0;
}

static PICO_REMOVE_RET pico_fan_remove(struct platform_device *pdev)
{
    sysfs_remove_group(&pdev->dev.kobj, &pico_fan_extra_group);
    dev_info(&pdev->dev, "pico_fan rimosso\n");
    PICO_RETURN_OK
}

static struct platform_driver pico_fan_driver = {
    .probe  = pico_fan_probe,
    .remove = pico_fan_remove,
    .driver = {
        .name  = DRIVER_NAME,
        .owner = THIS_MODULE,
    },
};

/* =========================================================================
 * Init / Exit
 * ====================================================================== */
static int __init pico_fan_init(void)
{
    int ret;

    pr_info("pico_fan: caricamento v%s (kernel %d.%d)\n",
            DRIVER_VERSION,
            LINUX_VERSION_MAJOR, LINUX_VERSION_PATCHLEVEL);

    ret = platform_driver_register(&pico_fan_driver);
    if (ret) {
        pr_err("pico_fan: errore registrazione driver: %d\n", ret);
        return ret;
    }

    pico_fan_pdev = platform_device_register_simple(DRIVER_NAME, -1, NULL, 0);
    if (IS_ERR(pico_fan_pdev)) {
        ret = PTR_ERR(pico_fan_pdev);
        pr_err("pico_fan: errore creazione device: %d\n", ret);
        platform_driver_unregister(&pico_fan_driver);
        return ret;
    }

    pr_info("pico_fan: modulo caricato\n");
    return 0;
}

static void __exit pico_fan_exit(void)
{
    platform_device_unregister(pico_fan_pdev);
    platform_driver_unregister(&pico_fan_driver);
    pr_info("pico_fan: modulo rimosso\n");
}

module_init(pico_fan_init);
module_exit(pico_fan_exit);

MODULE_AUTHOR("pico-fan-control project");
MODULE_DESCRIPTION("Driver HWMON virtuale per ventola USB Raspberry Pi Pico");
MODULE_LICENSE("GPL v2");
MODULE_VERSION(DRIVER_VERSION);
MODULE_ALIAS("platform:" DRIVER_NAME);
