/*
 * This Java source file was generated by the Gradle 'init' task.
 */
package app;

import org.junit.Test;
import static org.junit.Assert.*;
import org.junit.BeforeClass;

public class AppTest {
    @BeforeClass
    public static void checkBeforeClass() {
        System.out.println("I'm before class");
    }
    @Test
    public void doSomething() {
        System.out.println("Hi I'm test One");
    }
    @Test (timeout=5000)
    public void testAppHasAGreeting() {
        App classUnderTest = new App();
        assertNotNull("app should have a greeting", classUnderTest.getGreeting());
    }
}
